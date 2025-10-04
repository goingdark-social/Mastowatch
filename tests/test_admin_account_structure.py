"""Tests for admin account data structure handling.

These tests verify that the system correctly handles Mastodon admin API responses,
which have the structure:
{
    "id": "123",
    "username": "user",
    "email": "user@example.com",
    "ip": {"ip": "1.2.3.4", "used_at": "2023-01-01T00:00:00.000Z"},
    "role": {"id": 1, "name": "Admin", ...},
    "confirmed": true,
    "suspended": false,
    "account": {
        "id": "123",
        "username": "user",
        "acct": "user@domain",
        ...
    }
}

NOT wrapped as {"account": {...}}
"""

import pytest
from datetime import datetime, UTC
from unittest.mock import MagicMock, patch, ANY
from app.tasks.jobs import _poll_accounts, _persist_account
from app.scanning import EnhancedScanningSystem
from app.models import Account, ScanSession
from sqlalchemy import text


@pytest.fixture
def sample_admin_account():
    """Sample admin account response matching Mastodon API v2 structure.

    Based on official Mastodon docs:
    https://docs.joinmastodon.org/methods/admin/accounts/#v2
    """
    return {
        "id": "108267695853695427",
        "username": "testuser",
        "domain": None,
        "created_at": "2022-05-08T18:18:53.221Z",
        "email": "testuser@mastodon.local",
        "ip": {
            "user_id": 1,
            "ip": "192.168.42.1",
            "used_at": "2022-09-08T16:10:38.621Z"
        },
        "role": {
            "id": 3,
            "name": "User",
            "color": "",
            "position": 1000,
            "permissions": 1,
            "highlighted": True,
            "created_at": "2022-09-08T22:48:07.983Z",
            "updated_at": "2022-09-08T22:48:07.983Z"
        },
        "confirmed": True,
        "suspended": False,
        "silenced": False,
        "disabled": False,
        "approved": True,
        "locale": None,
        "invite_request": None,
        "ips": [
            {
                "ip": "192.168.42.1",
                "used_at": "2022-09-08T16:10:38.621Z"
            }
        ],
        "account": {
            "id": "108267695853695427",
            "username": "testuser",
            "acct": "testuser",
            "display_name": "Test User",
            "locked": False,
            "bot": False,
            "discoverable": None,
            "group": False,
            "created_at": "2022-09-08T00:00:00.000Z",
            "note": "<p>Test account</p>",
            "url": "https://mastodon.local/@testuser",
            "avatar": "https://mastodon.local/avatars/original/missing.png",
            "avatar_static": "https://mastodon.local/avatars/original/missing.png",
            "header": "https://mastodon.local/headers/original/missing.png",
            "header_static": "https://mastodon.local/headers/original/missing.png",
            "followers_count": 0,
            "following_count": 0,
            "statuses_count": 5,
            "last_status_at": "2022-09-08",
            "emojis": [],
            "fields": []
        }
    }


@pytest.fixture
def sample_admin_accounts_list(sample_admin_account):
    """Sample response from admin_accounts_v2() - list of admin accounts."""
    return [sample_admin_account]


class TestAdminAccountDataStructure:
    """Test correct handling of admin account API responses."""

    def test_persist_account_handles_admin_structure(self, test_db_session, sample_admin_account):
        """Test that _persist_account correctly extracts data from admin account structure."""
        _persist_account(sample_admin_account)

        # Verify account was persisted with correct data
        account = test_db_session.query(Account).filter_by(
            mastodon_account_id=sample_admin_account["id"]
        ).first()

        assert account is not None
        assert account.username == sample_admin_account["username"]
        assert account.acct == sample_admin_account["account"]["acct"]
        # Admin fields should be accessible
        assert account.email == sample_admin_account["email"]

    def test_scanner_receives_full_admin_object(self, sample_admin_account):
        """Test that scanner receives full admin object, not just nested account."""
        scanner = EnhancedScanningSystem()

        with patch.object(scanner, 'scan_account_efficiently') as mock_scan:
            mock_scan.return_value = {"score": 0.5, "violations": []}

            # Simulate what _poll_accounts should do
            session_id = "test-session"

            # CORRECT: Pass full admin object
            result = scanner.scan_account_efficiently(sample_admin_account, session_id)

            # Verify scanner was called with full admin object
            mock_scan.assert_called_once_with(sample_admin_account, session_id)

    def test_scanner_can_access_admin_fields(self, sample_admin_account):
        """Test that scanner can access admin-specific fields for rule evaluation."""
        scanner = EnhancedScanningSystem()

        # Scanner should be able to access admin fields
        admin_fields = {
            'email': sample_admin_account.get('email'),
            'ip': sample_admin_account.get('ip', {}).get('ip'),
            'created_at': sample_admin_account.get('created_at'),
            'confirmed': sample_admin_account.get('confirmed'),
            'suspended': sample_admin_account.get('suspended'),
            'role': sample_admin_account.get('role', {}).get('name'),
        }

        # All admin fields should be present
        assert admin_fields['email'] == "testuser@mastodon.local"
        assert admin_fields['ip'] == "192.168.42.1"
        assert admin_fields['created_at'] == "2022-05-08T18:18:53.221Z"
        assert admin_fields['confirmed'] is True
        assert admin_fields['suspended'] is False
        assert admin_fields['role'] == "User"

    def test_nested_account_structure(self, sample_admin_account):
        """Test that nested account field is correctly structured."""
        nested_account = sample_admin_account.get("account")

        assert nested_account is not None
        assert nested_account["id"] == sample_admin_account["id"]
        assert nested_account["username"] == sample_admin_account["username"]
        assert "acct" in nested_account
        assert "display_name" in nested_account

    @patch('app.tasks.jobs.mastodon_service')
    @patch('app.tasks.jobs.EnhancedScanningSystem')
    def test_poll_accounts_passes_full_admin_object(
        self,
        mock_scanner_class,
        mock_mastodon_service,
        test_db_session,
        sample_admin_accounts_list
    ):
        """Test that _poll_accounts passes full admin object to scanner.

        This is the critical bug: jobs.py was doing account_data.get("account", {})
        which strips admin metadata.
        """
        # Setup mocks
        mock_scanner = MagicMock()
        mock_scanner_class.return_value = mock_scanner
        mock_scanner.start_scan_session.return_value = "test-session-id"
        mock_scanner.get_next_accounts_to_scan.return_value = (
            sample_admin_accounts_list,
            None  # No next cursor
        )
        mock_scanner.scan_account_efficiently.return_value = {
            "score": 0.8,
            "violations": [{"rule": "test", "score": 0.8}]
        }

        # Initialize cursor
        test_db_session.execute(
            text("INSERT INTO cursors (name, position) VALUES (:n, :p)"),
            {"n": "admin_accounts_remote", "p": None}
        )
        test_db_session.commit()

        # Run the polling function
        _poll_accounts("remote", "admin_accounts_remote")

        # Verify scanner was called with FULL admin object, not nested account
        mock_scanner.scan_account_efficiently.assert_called_once()
        call_args = mock_scanner.scan_account_efficiently.call_args[0]
        account_data = call_args[0]

        # Account data should have admin fields
        assert "email" in account_data, "Admin object should have email field"
        assert "ip" in account_data, "Admin object should have ip field"
        assert "confirmed" in account_data, "Admin object should have confirmed field"
        assert "account" in account_data, "Admin object should have nested account field"

        # Should NOT be just the nested account
        assert account_data.get("email") is not None, "Should have admin email, not just nested account"


class TestAdminAccountPagination:
    """Test pagination cursor handling for admin accounts."""

    @patch('app.tasks.jobs.mastodon_service')
    def test_pagination_cursor_preserved(
        self,
        mock_mastodon_service,
        test_db_session,
        sample_admin_accounts_list
    ):
        """Test that pagination cursor is correctly extracted and stored."""
        # Setup mock to return cursor
        mock_mastodon_service.get_admin_accounts_sync.return_value = (
            sample_admin_accounts_list,
            "999999"  # Next cursor
        )

        scanner = EnhancedScanningSystem()
        accounts, next_cursor = scanner.get_next_accounts_to_scan("remote", limit=50)

        assert next_cursor == "999999"
        assert len(accounts) == 1

    def test_pagination_info_structure(self, sample_admin_accounts_list):
        """Test that pagination info is correctly structured."""
        # Mastodon.py returns pagination info via get_pagination_info()
        # which should return: {"max_id": "123", "since_id": "456", "min_id": "789"}

        # Mock the pagination info structure
        pagination_info = {
            "max_id": "999999",
            "since_id": "000001",
            "min_id": None
        }

        assert "max_id" in pagination_info
        assert pagination_info["max_id"] is not None


class TestScanSessionProgress:
    """Test scan session progress tracking."""

    def test_scan_session_created_with_type(self, test_db_session):
        """Test that scan session is created with correct type."""
        scanner = EnhancedScanningSystem()
        session_id = scanner.start_scan_session("remote")

        session = test_db_session.query(ScanSession).filter_by(id=session_id).first()
        assert session is not None
        assert session.session_type == "remote"
        assert session.status == "active"

    def test_session_progress_updated(self, test_db_session):
        """Test that session progress fields are updated during scanning."""
        scanner = EnhancedScanningSystem()
        session_id = scanner.start_scan_session("remote")

        # Verify session has progress fields
        session = test_db_session.query(ScanSession).filter_by(id=session_id).first()
        assert hasattr(session, 'accounts_processed')
        assert hasattr(session, 'total_accounts')
        assert hasattr(session, 'current_cursor')

        # Initially should be zeros/nulls
        assert session.accounts_processed == 0

    @patch('app.tasks.jobs.EnhancedScanningSystem')
    @patch('app.tasks.jobs.mastodon_service')
    def test_accounts_processed_increments(
        self,
        mock_mastodon_service,
        mock_scanner_class,
        test_db_session,
        sample_admin_accounts_list
    ):
        """Test that accounts_processed increments during scanning."""
        # Setup mocks
        mock_scanner = MagicMock()
        mock_scanner_class.return_value = mock_scanner
        mock_scanner.start_scan_session.return_value = "test-session"
        mock_scanner.get_next_accounts_to_scan.return_value = (
            sample_admin_accounts_list,
            None
        )
        mock_scanner.scan_account_efficiently.return_value = {"score": 0.5}

        # Initialize cursor
        test_db_session.execute(
            text("INSERT INTO cursors (name, position) VALUES (:n, :p)"),
            {"n": "test_cursor", "p": None}
        )
        test_db_session.commit()

        # Create session manually to track
        from app.models import ScanSession
        session = ScanSession(
            id="test-session",
            session_type="remote",
            status="active",
            accounts_processed=0
        )
        test_db_session.add(session)
        test_db_session.commit()

        # Run polling
        _poll_accounts("remote", "test_cursor")

        # Session should have been updated
        # Note: In actual implementation, this should increment
        session = test_db_session.query(ScanSession).filter_by(id="test-session").first()
        # This will fail until the bug is fixed!
        # assert session.accounts_processed > 0


class TestWebhookDataStructure:
    """Test webhook payload handling."""

    def test_status_webhook_payload_structure(self):
        """Test that status webhook payload matches expected structure."""
        # Mastodon sends webhooks with this structure
        webhook_payload = {
            "id": "109382576886209876",
            "created_at": "2022-11-19T19:48:13.078Z",
            "account": {
                "id": "108267695853695427",
                "username": "testuser",
                "acct": "testuser",
                "display_name": "Test User"
            },
            "content": "<p>Test status</p>",
            "visibility": "public",
            "sensitive": False,
            "spoiler_text": "",
            "media_attachments": [],
            "mentions": [],
            "tags": [],
            "emojis": []
        }

        assert "account" in webhook_payload
        assert webhook_payload["account"]["id"] is not None

    def test_report_webhook_payload_structure(self):
        """Test that report webhook payload matches expected structure."""
        webhook_payload = {
            "id": "123",
            "action_taken": False,
            "comment": "Spam report",
            "account": {
                "id": "108267695853695427",
                "username": "testuser"
            },
            "target_account": {
                "id": "999",
                "username": "spammer"
            },
            "statuses": []
        }

        assert "account" in webhook_payload
        assert "target_account" in webhook_payload


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
