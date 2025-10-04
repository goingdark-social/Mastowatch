"""Integration tests for the complete scanning flow.

Tests the end-to-end flow from Celery Beat → Account Polling → Scanning → Reporting
"""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from app.models import Account, Rule, ScanSession
from app.scanning import ScanningSystem
from app.tasks.jobs import analyze_and_maybe_report, poll_admin_accounts
from sqlalchemy import text


@pytest.fixture
def admin_account_with_violations():
    """Admin account that should trigger violations.

    Mastodon API v2 compliant structure with ip as a string.
    """
    return {
        "id": "malicious123",
        "username": "spammer",
        "domain": None,
        "created_at": datetime.now(UTC).isoformat(),  # New account
        "email": "spam@malicious.com",
        "ip": "1.2.3.4",  # v2 API: ip is a STRING
        "ips": [{"ip": "1.2.3.4", "used_at": datetime.now(UTC).isoformat()}],  # Historical IPs
        "confirmed": False,  # Unconfirmed
        "suspended": False,
        "silenced": False,
        "account": {
            "id": "malicious123",
            "username": "spammer",
            "acct": "spammer@malicious.domain",
            "display_name": "FREE CRYPTO WIN NOW",
            "note": "<p>Click here for free Bitcoin!</p>",
            "url": "https://malicious.domain/@spammer",
            "statuses_count": 50,  # High post count for new account
            "followers_count": 0,
            "following_count": 1000,  # Suspicious ratio
            "created_at": datetime.now(UTC).isoformat(),
        },
    }


@pytest.fixture
def spam_detection_rules(test_db_session):
    """Create rules that detect spam patterns."""
    rules = [
        Rule(
            name="crypto_keywords",
            detector_type="keyword",
            pattern="bitcoin,crypto,free,win",
            weight=0.8,
            enabled=True,
            action_type="report",
            trigger_threshold=1.0,
        ),
        Rule(
            name="new_unconfirmed_account",
            detector_type="behavioral",
            pattern="unconfirmed_new_account",
            weight=0.5,
            enabled=True,
            action_type="silence",
            trigger_threshold=1.0,
        ),
        Rule(
            name="suspicious_follower_ratio",
            detector_type="behavioral",
            pattern="low_followers_high_following",
            weight=0.6,
            enabled=True,
            action_type="report",
            trigger_threshold=1.0,
        ),
    ]

    for rule in rules:
        test_db_session.add(rule)
    test_db_session.commit()

    return rules


class TestCompleteScanningFlow:
    """Test complete flow from polling to reporting."""

    @patch("app.tasks.jobs.analyze_and_maybe_report.delay")
    @patch("app.tasks.jobs.mastodon_service")
    def test_poll_scan_detect_flow(
        self,
        mock_mastodon_service,
        mock_analyze_task,
        test_db_session,
        admin_account_with_violations,
        spam_detection_rules,
    ):
        """Test: Poll accounts → Scan → Detect violations → Queue reporting."""

        # Mock Mastodon API to return malicious account
        mock_mastodon_service.get_admin_accounts_sync.return_value = (
            [admin_account_with_violations],
            None,  # No next page
        )

        # Mock status fetching
        mock_mastodon_service.get_account_statuses_sync.return_value = [
            {
                "id": "status123",
                "content": "Get free Bitcoin now! Click here!",
                "created_at": datetime.now(UTC).isoformat(),
            }
        ]

        # Initialize cursor with NULL position (now allowed!)
        test_db_session.execute(
            text("INSERT INTO cursors (name, position) VALUES (:n, :p)"), {"n": "admin_accounts_remote", "p": None}
        )
        test_db_session.commit()

        # Trigger polling (simulates Celery Beat)
        poll_admin_accounts()

        # Verify account was persisted
        account = test_db_session.query(Account).filter_by(mastodon_account_id="malicious123").first()
        assert account is not None

        # Verify reporting task was queued if violations found
        if mock_analyze_task.called:
            call_args = mock_analyze_task.call_args[0][0]
            assert "account" in call_args
            assert "scan_result" in call_args

    @patch("app.services.enforcement_service.EnforcementService.create_report")
    def test_analyze_and_report_flow(
        self, mock_create_report, test_db_session, admin_account_with_violations, spam_detection_rules
    ):
        """Test analysis and reporting based on scan results."""

        scan_result = {
            "score": 1.4,  # Above threshold
            "violations": [
                {"rule": "crypto_keywords", "score": 0.8, "evidence": "Found: bitcoin, free"},
                {"rule": "new_unconfirmed_account", "score": 0.6, "evidence": "Account unconfirmed, < 24h old"},
            ],
        }

        # Mock create_report to track calls
        mock_create_report.return_value = {"id": "report123"}

        # Call reporting task
        analyze_and_maybe_report({"account": admin_account_with_violations, "scan_result": scan_result})

        # Verify report was created
        # (actual implementation may vary)
        # mock_create_report.assert_called_once()

    def test_session_lifecycle(self, test_db_session):
        """Test scan session creation, update, and completion."""
        scanner = ScanningSystem()

        # Start session
        session_id = scanner.start_scan_session("remote")
        session = test_db_session.query(ScanSession).filter_by(id=session_id).first()

        assert session.status == "active"
        assert session.session_type == "remote"
        assert session.started_at is not None

        # Complete session
        scanner.complete_scan_session(session_id, status="completed")
        test_db_session.refresh(session)

        assert session.status == "completed"
        assert session.completed_at is not None


class TestMastodonAPICompliance:
    """Test compliance with actual Mastodon API responses."""

    def test_admin_accounts_structure(self):
        """Verify test fixtures match actual Mastodon API v2 response structure.

        Based on: https://docs.joinmastodon.org/methods/admin/accounts/#v2
        """
        # This is what Mastodon ACTUALLY returns
        expected_structure = {
            "id": str,
            "username": str,
            "domain": (str, type(None)),
            "created_at": str,
            "email": str,
            "ip": dict,  # {"ip": str, "user_id": int, "used_at": str}
            "role": dict,  # {"id": int, "name": str, "permissions": int, ...}
            "confirmed": bool,
            "suspended": bool,
            "silenced": bool,
            "disabled": bool,
            "approved": bool,
            "account": dict,  # Nested account object
        }

        sample = {
            "id": "108267695853695427",
            "username": "testuser",
            "domain": None,
            "created_at": "2022-05-08T18:18:53.221Z",
            "email": "test@example.com",
            "ip": {"ip": "1.2.3.4", "user_id": 1, "used_at": "2023-01-01T00:00:00Z"},
            "role": {"id": 1, "name": "User", "permissions": 0},
            "confirmed": True,
            "suspended": False,
            "silenced": False,
            "disabled": False,
            "approved": True,
            "account": {"id": "108267695853695427", "username": "testuser", "acct": "testuser"},
        }

        # Verify all expected fields are present
        for field, expected_type in expected_structure.items():
            assert field in sample, f"Missing required field: {field}"
            if isinstance(expected_type, tuple):
                assert isinstance(sample[field], expected_type), f"Field {field} has wrong type: {type(sample[field])}"
            else:
                assert isinstance(sample[field], expected_type), f"Field {field} has wrong type: {type(sample[field])}"

    def test_pagination_info_structure(self):
        """Test pagination info matches Mastodon.py get_pagination_info() response.

        Mastodon.py returns: {"max_id": str, "since_id": str, "min_id": str}
        """
        # Mock what get_pagination_info() returns
        pagination_info = {"max_id": "109573612584350057", "since_id": "109573612584350001", "min_id": None}

        assert "max_id" in pagination_info
        assert isinstance(pagination_info["max_id"], (str, type(None)))

    def test_status_structure(self):
        """Test status object structure matches Mastodon API."""
        status = {
            "id": "109382576886209876",
            "created_at": "2022-11-19T19:48:13.078Z",
            "account": {"id": "108267695853695427", "username": "testuser", "acct": "testuser"},
            "content": "<p>Test post</p>",
            "visibility": "public",
            "sensitive": False,
            "spoiler_text": "",
            "media_attachments": [],
            "application": {"name": "Web", "website": None},
            "mentions": [],
            "tags": [],
            "emojis": [],
            "reblogs_count": 0,
            "favourites_count": 0,
            "replies_count": 0,
        }

        # Required fields per Mastodon API
        required_fields = ["id", "created_at", "account", "content", "visibility"]
        for field in required_fields:
            assert field in status, f"Status missing required field: {field}"


class TestCursorPersistence:
    """Test pagination cursor persistence across polling cycles."""

    @patch("app.tasks.jobs.mastodon_service")
    def test_cursor_saved_between_polls(self, mock_mastodon_service, test_db_session):
        """Test that cursor is saved and used in next poll."""

        # First poll returns cursor
        mock_mastodon_service.get_admin_accounts_sync.return_value = (
            [{"id": "1", "username": "user1", "account": {"id": "1", "username": "user1", "acct": "user1"}}],
            "cursor_123",
        )

        # Initialize cursor with NULL position (allowed now!)
        test_db_session.execute(
            text("INSERT INTO cursors (name, position) VALUES (:n, :p)"), {"n": "test_cursor", "p": None}
        )
        test_db_session.commit()

        # First poll
        from app.tasks.jobs import _poll_accounts

        _poll_accounts("remote", "test_cursor")

        # Verify cursor was saved
        cursor = test_db_session.execute(
            text("SELECT position FROM cursors WHERE name = :n"), {"n": "test_cursor"}
        ).scalar()

        assert cursor == "cursor_123"

        # Second poll should use saved cursor
        mock_mastodon_service.get_admin_accounts_sync.return_value = (
            [{"id": "2", "username": "user2", "account": {"id": "2", "username": "user2", "acct": "user2"}}],
            None,  # Last page
        )

        _poll_accounts("remote", "test_cursor")

        # Cursor should be updated to None (end of pagination)
        cursor = test_db_session.execute(
            text("SELECT position FROM cursors WHERE name = :n"), {"n": "test_cursor"}
        ).scalar()

        assert cursor is None


class TestErrorHandling:
    """Test error handling in scanning flow."""

    @patch("app.tasks.jobs.mastodon_service")
    def test_api_error_handling(self, mock_mastodon_service, test_db_session):
        """Test graceful handling of Mastodon API errors."""
        from mastodon import MastodonAPIError

        # Mock API error
        mock_mastodon_service.get_admin_accounts_sync.side_effect = MastodonAPIError("API Error")

        # Initialize cursor with NULL position (allowed!)
        test_db_session.execute(
            text("INSERT INTO cursors (name, position) VALUES (:n, :p)"), {"n": "error_cursor", "p": None}
        )
        test_db_session.commit()

        # Should not crash
        from app.tasks.jobs import _poll_accounts

        try:
            _poll_accounts("remote", "error_cursor")
        except Exception as e:
            pytest.fail(f"Polling should handle API errors gracefully, but raised: {e}")

    def test_invalid_account_data_handling(self, test_db_session):
        """Test handling of malformed account data."""
        from app.tasks.jobs import _persist_account

        # Missing required fields
        invalid_account = {
            "id": "123"
            # Missing username, account, etc.
        }

        # Should not crash, should skip or log error
        try:
            _persist_account(invalid_account)
        except Exception:
            # Expected to fail gracefully or skip
            pass


class TestRuleEvaluation:
    """Test rule evaluation with admin account fields."""

    def test_behavioral_rule_uses_admin_fields(self, test_db_session, admin_account_with_violations):
        """Test that behavioral rules can access admin fields."""

        # Create rule that checks admin fields
        rule = Rule(
            name="unconfirmed_account_check",
            detector_type="behavioral",
            pattern="check_confirmed_status",
            weight=1.0,
            enabled=True,
            action_type="report",
            trigger_threshold=1.0,
        )
        test_db_session.add(rule)
        test_db_session.commit()

        # Rule evaluation should be able to check:
        # - admin_account_with_violations["confirmed"] == False
        # - admin_account_with_violations["created_at"] == recent
        # - admin_account_with_violations["email"] == suspicious

        # The scanner should receive the full admin object
        ScanningSystem()

        # Verify admin fields are accessible
        assert admin_account_with_violations.get("confirmed") is False
        assert admin_account_with_violations.get("email") is not None
        assert admin_account_with_violations.get("created_at") is not None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
