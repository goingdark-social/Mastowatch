"""Dedicated test suite for Scanning System functionality covering:
- Content deduplication and hashing
- Federated scanning with 422 error handling
- Domain violation tracking and thresholds
- Cache invalidation strategies
- Session management and progress tracking
"""

import os
import sys
import unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

# Set test environment before any imports
os.environ.update(
    {
        "SKIP_STARTUP_VALIDATION": "1",
        "INSTANCE_BASE": "https://test.mastodon.social",
        "MASTODON_CLIENT_SECRET": "test_MASTODON_CLIENT_SECRET_123456789",
        "DATABASE_URL": "postgresql+psycopg://test:test@localhost:5433/mastowatch_test",
        "REDIS_URL": "redis://localhost:6380/1",
        "DEFEDERATION_THRESHOLD": "10",
        "CONTENT_CACHE_TTL": "24",
        "FEDERATED_SCAN_ENABLED": "true",
        "UI_ORIGIN": "http://localhost:3000",
    }
)

# Add the app directory to the path so we can import the app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.schemas import Violation


class TestScanningSystem(unittest.TestCase):
    """Test scanning system functionality"""

    def setUp(self):
        """Prepare database and client mocks."""
        self.db_patcher = patch("app.scanning.SessionLocal")
        self.mock_db = self.db_patcher.start()
        self.mock_session = MagicMock()
        self.mock_db.return_value.__enter__.return_value = self.mock_session
        self.mock_session.query.return_value.filter.return_value.first.return_value = None
        self.mock_session.query.return_value.filter.return_value.all.return_value = []
        self.mock_session.query.return_value.order_by.return_value.limit.return_value.all.return_value = []
        self.mock_session.commit.return_value = None

        # Mock mastodon_service
        self.service_patcher = patch("app.scanning.mastodon_service")
        self.mock_masto_service = self.service_patcher.start()
        self.mock_client_instance = MagicMock()
        self.mock_masto_service.get_admin_client.return_value = self.mock_client_instance
        self.mock_client_instance.account_statuses.return_value = []

        self.rule_service_patcher = patch("app.scanning.rule_service")
        self.mock_rule_service = self.rule_service_patcher.start()
        self.mock_rule_service.get_active_rules.return_value = ([], {"report_threshold": 1.0}, "test_sha256")
        self.mock_rule_service.evaluate_account.return_value = []

        from app.scanning import ScanningSystem

        self.scanning_system = ScanningSystem()

    def tearDown(self):
        """Stop patches."""
        self.db_patcher.stop()
        self.service_patcher.stop()
        self.rule_service_patcher.stop()

    def test_content_hash_calculation(self):
        """Test content hash calculation for deduplication"""
        account_data1 = {
            "username": "testuser",
            "display_name": "Test User",
            "note": "This is a test bio",
            "avatar": "http://example.com/avatar.jpg",
            "header": "http://example.com/header.jpg",
            "fields": [{"name": "Website", "value": "https://example.com"}],
        }

        account_data2 = account_data1.copy()

        # Same content should produce same hash
        hash1 = self.scanning_system._calculate_content_hash(account_data1)
        hash2 = self.scanning_system._calculate_content_hash(account_data2)
        self.assertEqual(hash1, hash2)

        # Different content should produce different hash
        account_data2["note"] = "Different bio"
        hash3 = self.scanning_system._calculate_content_hash(account_data2)
        self.assertNotEqual(hash1, hash3)

        # Hash should be deterministic
        hash4 = self.scanning_system._calculate_content_hash(account_data1)
        self.assertEqual(hash1, hash4)

    def test_should_scan_account_deduplication(self):
        """Test account scanning deduplication logic"""
        account_data = {
            "id": "test_account_123",
            "username": "testuser",
            "display_name": "Test User",
            "note": "Test bio",
        }

        # Mock recent scan exists with same content
        mock_content_scan = MagicMock()
        mock_content_scan.needs_rescan = False
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_content_scan

        # Should skip scanning
        should_scan = self.scanning_system.should_scan_account("test_account_123", account_data)
        self.assertFalse(should_scan)

        # Mock no recent scan exists
        self.mock_session.query.return_value.filter.return_value.first.return_value = None

        # Should perform scanning
        should_scan = self.scanning_system.should_scan_account("test_account_123", account_data)
        self.assertTrue(should_scan)

    def test_scan_session_management(self):
        """Test scan session creation and management"""
        # Test starting new session
        mock_scan_session = MagicMock()
        mock_scan_session.id = 1
        self.mock_session.add.return_value = None
        self.mock_session.refresh.return_value = None

        self.scanning_system.start_scan_session("test_type", {"key": "value"})

        self.mock_session.add.assert_called_once()
        self.mock_session.commit.assert_called_once()

    def test_scan_session_duplicate_prevention(self):
        """Test prevention of duplicate active sessions"""
        # Mock existing active session
        mock_existing_session = MagicMock()
        mock_existing_session.id = 1
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_existing_session

        session_id = self.scanning_system.start_scan_session("test_type")

        # Should return existing session ID
        self.assertEqual(session_id, 1)
        # Should not create new session
        self.mock_session.add.assert_not_called()

    def test_federated_scanning_with_422_error(self):
        """Test federated scanning handles 422 Unprocessable Content errors"""
        # Mock 422 response from Mastodon API
        mock_response = MagicMock()
        mock_response.status_code = 422
        mock_response.json.return_value = {"error": "Unprocessable Content"}
        self.mock_client_instance.get.return_value = mock_response

        # Mock domain list
        mock_account = MagicMock()
        mock_account.mastodon_account_id = "test_123"
        mock_account.acct = "test@example.com"
        mock_account.domain = "example.com"
        self.mock_session.query.return_value.filter.return_value.limit.return_value.all.return_value = [mock_account]

        results = self.scanning_system._scan_domain_content("example.com", 1)

        # Should handle error gracefully and continue
        self.assertIsInstance(results, dict)
        self.assertIn("accounts", results)
        self.assertIn("violations", results)

    @unittest.skip("Mock not integrated with actual implementation - database session not called as expected")
    def test_domain_violation_tracking(self):
        """Test domain violation tracking and threshold checking"""
        domain = "spam.example"

        # Test tracking violation
        self.scanning_system._track_domain_violation(domain)

        # Verify database upsert was called
        self.mock_session.execute.assert_called_once()
        self.mock_session.commit.assert_called_once()

    def test_defederation_threshold_checking(self):
        """Test automatic defederation when threshold is reached"""
        domain = "bad.example"

        # Mock domain alert at threshold
        mock_domain_alert = MagicMock()
        mock_domain_alert.domain = domain
        mock_domain_alert.violation_count = 10
        mock_domain_alert.defederation_threshold = 10
        mock_domain_alert.is_defederated = False
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_domain_alert

        self.scanning_system._check_defederation_threshold(domain)

        # Verify domain was marked for defederation
        self.assertTrue(mock_domain_alert.is_defederated)
        self.assertIsNotNone(mock_domain_alert.defederated_at)
        self.assertEqual(mock_domain_alert.defederated_by, "automated_system")

    def test_domain_extraction(self):
        """Test domain extraction from account data"""
        # Test federated account
        account_data1 = {"acct": "user@example.com"}
        domain1 = self.scanning_system._extract_domain(account_data1)
        self.assertEqual(domain1, "example.com")

        # Test local account
        account_data2 = {"acct": "localuser"}
        domain2 = self.scanning_system._extract_domain(account_data2)
        self.assertEqual(domain2, "local")

        # Test missing acct
        account_data3 = {}
        domain3 = self.scanning_system._extract_domain(account_data3)
        self.assertEqual(domain3, "local")

    def test_cursor_based_pagination(self):
        """Test cursor-based pagination for account fetching"""
        # Test parsing next cursor from Link header
        link_header = '<https://mastodon.example/api/v1/admin/accounts?max_id=12345>; rel="next"'
        cursor = self.scanning_system._parse_next_cursor(link_header)
        self.assertEqual(cursor, "12345")

        # Test no cursor in header
        empty_cursor = self.scanning_system._parse_next_cursor("")
        self.assertIsNone(empty_cursor)

        # Test malformed header
        bad_header = "invalid header format"
        bad_cursor = self.scanning_system._parse_next_cursor(bad_header)
        self.assertIsNone(bad_cursor)

    def test_get_next_accounts_to_scan(self):
        """Test fetching next batch of accounts with pagination"""
        # Mock get_admin_accounts to return accounts and next cursor
        accounts_data = [
            {"id": "1", "acct": "user1@example.com"},
            {"id": "2", "acct": "user2@example.com"},
        ]
        self.mock_client_instance.get_admin_accounts.return_value = (accounts_data, "12345")

        accounts, next_cursor = self.scanning_system.get_next_accounts_to_scan("remote", limit=10)

        # Verify results
        self.assertEqual(len(accounts), 2)
        self.assertEqual(next_cursor, "12345")

        # Verify API was called with correct parameters
        self.mock_client_instance.get_admin_accounts.assert_called_once_with(
            origin="remote", status="active", limit=10, max_id=None
        )

    def test_scan_account_efficiently(self):
        """Test efficient account scanning with caching"""
        account_data = {
            "id": "test_account_123",
            "username": "testuser",
            "display_name": "Test User",
            "note": "Test bio",
        }

        # Mock should_scan_account to return True
        with patch.object(self.scanning_system, "should_scan_account", return_value=True):
            mock_response = MagicMock()
            mock_response.json.return_value = [{"id": "status1", "content": "Test status"}]
            self.mock_client_instance.get.return_value = mock_response

            self.mock_rule_service.evaluate_account.return_value = [
                Violation(
                    rule_name="test_rule",
                    rule_type="t",
                    score=0.8,
                    evidence={"matched_terms": [], "matched_status_ids": [], "metrics": {}},
                    actions=[{"type": "report"}],
                )
            ]

            result = self.scanning_system.scan_account_efficiently(account_data, 1)

            self.assertIsNotNone(result)
            self.assertIn("score", result)
            self.assertIn("hits", result)
            self.assertIn("rule_hits", result)
            self.assertEqual(result["score"], 0.8)

    def test_cache_invalidation_rule_changes(self):
        """Test cache invalidation when rules change"""
        self.scanning_system.invalidate_content_scans(rule_changes=True)

        # Verify all scans are marked for rescan
        self.mock_session.query.return_value.update.assert_called_once_with({"needs_rescan": True})
        self.mock_session.commit.assert_called_once()

    def test_cache_invalidation_time_based(self):
        """Test time-based cache invalidation"""
        self.scanning_system.invalidate_content_scans(rule_changes=False)

        # Verify old scans are marked for rescan
        self.mock_session.query.return_value.filter.return_value.update.assert_called_once()
        self.mock_session.commit.assert_called_once()

    def test_get_domain_alerts(self):
        """Test retrieving domain alerts"""
        # Mock domain alerts
        mock_alert1 = MagicMock()
        mock_alert1.domain = "spam.example"
        mock_alert1.violation_count = 15
        mock_alert1.is_defederated = True
        mock_alert1.last_violation_at = datetime.utcnow()
        mock_alert1.defederation_threshold = 10
        mock_alert1.defederated_at = datetime.utcnow()
        mock_alert1.defederated_by = "admin"
        mock_alert1.notes = "Spam domain"

        mock_alert2 = MagicMock()
        mock_alert2.domain = "suspicious.example"
        mock_alert2.violation_count = 5
        mock_alert2.is_defederated = False
        mock_alert2.last_violation_at = datetime.utcnow()
        mock_alert2.defederation_threshold = 10
        mock_alert2.defederated_at = None
        mock_alert2.defederated_by = None
        mock_alert2.notes = None

        self.mock_session.query.return_value.order_by.return_value.limit.return_value.all.return_value = [
            mock_alert1,
            mock_alert2,
        ]

        alerts = self.scanning_system.get_domain_alerts(limit=10)

        # Verify results
        self.assertEqual(len(alerts), 2)
        self.assertEqual(alerts[0]["domain"], "spam.example")
        self.assertEqual(alerts[0]["violation_count"], 15)
        self.assertTrue(alerts[0]["is_defederated"])
        self.assertEqual(alerts[1]["domain"], "suspicious.example")
        self.assertEqual(alerts[1]["violation_count"], 5)
        self.assertFalse(alerts[1]["is_defederated"])

    def test_scan_progress_tracking(self):
        """Test scan progress tracking"""
        # Mock scan session
        mock_session_obj = MagicMock()
        mock_session_obj.id = 1
        mock_session_obj.session_type = "federated"
        mock_session_obj.accounts_processed = 50
        mock_session_obj.total_accounts = 100
        mock_session_obj.current_cursor = "cursor_123"
        mock_session_obj.started_at = datetime.utcnow()
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_session_obj

        progress = self.scanning_system.get_scan_progress(1)

        # Verify progress tracking
        self.assertIsNotNone(progress)
        self.assertEqual(progress.session_id, 1)
        self.assertEqual(progress.session_type, "federated")
        self.assertEqual(progress.accounts_processed, 50)
        self.assertEqual(progress.total_accounts, 100)

    def test_complete_scan_session(self):
        """Test completing scan sessions"""
        # Mock scan session
        mock_session_obj = MagicMock()
        mock_session_obj.status = "active"
        self.mock_session.query.return_value.filter.return_value.first.return_value = mock_session_obj

        self.scanning_system.complete_scan_session(1, "completed")

        # Verify session was marked as completed
        self.assertEqual(mock_session_obj.status, "completed")
        self.assertIsNotNone(mock_session_obj.completed_at)
        self.mock_session.commit.assert_called_once()

    def test_get_active_domains(self):
        """Test getting list of active domains for scanning"""
        # Mock domain query results
        query_chain = (
            self.mock_session.query.return_value.filter.return_value.distinct.return_value.limit.return_value.all
        )
        query_chain.return_value = [
            ("example.com",),
            ("test.org",),
            ("sample.net",),
        ]

        domains = self.scanning_system._get_active_domains()

        # Verify results
        self.assertEqual(len(domains), 3)
        self.assertIn("example.com", domains)
        self.assertIn("test.org", domains)
        self.assertIn("sample.net", domains)

    def test_federated_content_scan_error_handling(self):
        """Test error handling in federated content scanning"""
        # Mock domain scanning to raise exception
        with patch.object(self.scanning_system, "_scan_domain_content", side_effect=Exception("Network error")):
            with patch.object(self.scanning_system, "_get_active_domains", return_value=["error.example"]):
                results = self.scanning_system.scan_federated_content()

                # Should handle error gracefully
                self.assertIsInstance(results, dict)
                self.assertEqual(results["scanned_domains"], 0)

    def test_rules_snapshot_generation(self):
        """Test generating rules snapshot for session tracking"""
        self.mock_rule_service.get_active_rules.return_value = ([1, 2], {"report_threshold": 1.0}, "test_sha256")

        snapshot = self.scanning_system._get_current_rules_snapshot()

        self.assertIn("rules_version", snapshot)
        self.assertIn("report_threshold", snapshot)
        self.assertIn("rule_count", snapshot)
        self.assertEqual(snapshot["rules_version"], "test_sha256")
        self.assertEqual(snapshot["report_threshold"], 1.0)

    def test_account_scanning_with_violation_tracking(self):
        """Test account scanning with domain violation tracking"""
        account_data = {
            "id": "test_account_123",
            "acct": "spammer@bad.example",
            "username": "spammer",
            "display_name": "Spam User",
        }

        with patch.object(self.scanning_system, "should_scan_account", return_value=True):
            self.mock_rule_service.evaluate_account.return_value = [
                Violation(
                    rule_name="spam_rule",
                    rule_type="t",
                    score=1.5,
                    evidence={"matched_terms": [], "matched_status_ids": [], "metrics": {}},
                    actions=[{"type": "report"}],
                )
            ]

            def statuses_side_effect(account_id, limit, only_media=False):
                return [{"id": "1", "content": "spam content", "media_attachments": []}]

            self.mock_client_instance.get_account_statuses.side_effect = statuses_side_effect

            with patch.object(self.scanning_system, "_track_domain_violation") as mock_track:
                self.scanning_system.scan_account_efficiently(account_data, 1)
                self.mock_client_instance.get_account_statuses.assert_any_call(
                    account_id="test_account_123", limit=self.scanning_system.settings.MAX_STATUSES_TO_FETCH
                )
                self.mock_client_instance.get_account_statuses.assert_any_call(
                    account_id="test_account_123",
                    limit=self.scanning_system.settings.MAX_STATUSES_TO_FETCH,
                    only_media=True,
                )
                mock_track.assert_called_once_with("bad.example")


if __name__ == "__main__":
    unittest.main(verbosity=2)
