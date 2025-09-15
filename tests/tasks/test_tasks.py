"""Tests for Celery task handlers."""

import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, call, patch

sys.path.insert(0, str(Path(__file__).parent.parent))

import app.tasks.jobs as jobs
from app.schemas import Violation
from app.tasks.jobs import (
    CURSOR_NAME,
    CURSOR_NAME_LOCAL,
    _poll_accounts,
    analyze_and_maybe_report,
    poll_admin_accounts,
    poll_admin_accounts_local,
    process_new_report,
    process_new_status,
)


class TestCeleryTasks(unittest.TestCase):
    """Celery task tests."""

    @patch("app.tasks.jobs.SessionLocal")
    @patch("app.tasks.jobs.rule_service")
    @patch("app.tasks.jobs.get_settings")
    @patch("app.tasks.jobs._get_bot_client")
    def test_analyze_and_maybe_report_dry_run(self, mock_bot_client, mock_settings, mock_rule_service, mock_db):
        """Test analyze_and_maybe_report in dry run mode"""
        # Setup mocks
        mock_settings.return_value.DRY_RUN = True
        mock_settings.return_value.PANIC_STOP = False

        # Mock rule service evaluation
        mock_rule_service.evaluate_account.return_value = [
            Violation(
                rule_name="rule1",
                rule_type="t1",
                score=0.5,
                evidence={"matched_terms": [], "matched_status_ids": [], "metrics": {}},
                actions=[{"type": "report"}],
            ),
            Violation(
                rule_name="rule2",
                rule_type="t2",
                score=0.3,
                evidence={"matched_terms": [], "matched_status_ids": [], "metrics": {}},
                actions=[{"type": "report"}],
            ),
        ]
        
        # Mock rule service get_active_rules
        mock_rule_service.get_active_rules.return_value = ([], {"report_threshold": 1.0}, "test_sha")

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock bot client
        mock_client = MagicMock()
        mock_bot_client.return_value = mock_client

        # Test data
        payload = {
            "account": {
                "id": "123456",
                "acct": "suspicious@example.com",
                "domain": "example.com",
            },
            "statuses": [{"id": "status1", "content": "spam content"}],
        }

        # Call the function
        result = analyze_and_maybe_report(payload)

        # Assertions for dry run mode - should return None
        self.assertIsNone(result)
        mock_rule_service.evaluate_account.assert_called_once()

        # Verify that database operations were called for analysis records
        self.assertTrue(mock_db_session.execute.called)
        self.assertTrue(mock_db_session.commit.called)

        # In dry run mode, should not actually submit reports
        mock_client.create_report.assert_not_called()

    @patch("app.tasks.jobs.SessionLocal")
    @patch("app.tasks.jobs.rule_service")
    @patch("app.tasks.jobs.settings")
    def test_analyze_and_maybe_report_panic_stop(self, mock_settings, mock_rule_service, mock_db):
        """Test that panic stop prevents execution"""
        # Setup mocks
        mock_settings.PANIC_STOP = True

        # Test data
        payload = {"account": {"id": "123456"}, "statuses": []}

        analyze_and_maybe_report(payload)

        mock_rule_service.evaluate_account.assert_not_called()
        mock_db.assert_not_called()

    @patch("app.tasks.jobs.SessionLocal")
    @patch("app.tasks.jobs.analyze_and_maybe_report")
    def test_process_new_report(self, mock_analyze, mock_db):
        """Test processing of new report webhook"""
        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        mock_analyze.delay.return_value = MagicMock(id="task_123")

        # Mock report payload
        payload = {
            "id": "report_123",
            "account": {"id": "reporter_123", "acct": "reporter@example.com"},
            "target_account": {"id": "target_123", "acct": "target@example.com"},
            "status_ids": ["status_1", "status_2"],
            "comment": "This is spam",
        }

        # Call the function
        result = process_new_report(payload)

        # Should trigger analysis of the target account
        self.assertIsNotNone(result)

    @patch("app.tasks.jobs.rule_service")
    @patch("app.tasks.jobs._get_admin_client")
    def test_process_new_status(self, mock_get_admin_client, mock_rule_service):
        """Test processing of new status webhook"""
        mock_client = MagicMock()
        mock_client.get_account_statuses.return_value = [
            {"id": "old1", "visibility": "public"},
            {"id": "old2", "visibility": "unlisted"},
            {"id": "status_123", "visibility": "public"},
            {"id": "old3", "visibility": "private"},
        ]
        mock_get_admin_client.return_value = mock_client
        mock_rule_service.evaluate_account.return_value = []

        payload = {
            "status": {
                "id": "status_123",
                "account": {"id": "account_123", "acct": "user@example.com"},
                "content": "test",
                "visibility": "public",
            }
        }

        process_new_status(payload)

        mock_client.get_account_statuses.assert_called_once_with(
            account_id="account_123", limit=20, exclude_reblogs=True
        )
        statuses_arg = mock_rule_service.evaluate_account.call_args[0][1]
        self.assertEqual({s["id"] for s in statuses_arg}, {"status_123", "old1", "old2"})
        account_arg = mock_rule_service.evaluate_account.call_args[0][0]
        self.assertEqual(
            {s["id"] for s in account_arg["recent_public_statuses"]},
            {"status_123", "old1"},
        )

    def test_analyze_and_maybe_report_invalid_payload(self):
        """Test handling of invalid payload"""
        # Test with missing account
        result = analyze_and_maybe_report({})

        # Should handle gracefully
        self.assertIsNone(result)

        # Test with invalid account data
        result = analyze_and_maybe_report({"account": None})
        self.assertIsNone(result)

    @patch("app.scanning.SessionLocal")
    @patch("app.tasks.jobs.SessionLocal")
    @patch("app.tasks.jobs.rule_service")
    @patch("app.tasks.jobs.settings")
    @patch("app.tasks.jobs._get_bot_client")
    @patch("app.tasks.jobs._get_admin_client")
    def test_analyze_and_maybe_report_report_creation(self, mock_admin_client, mock_bot_client, mock_settings, mock_rule_service, mock_db, mock_scanning_db):
        """Test that reports are created when score exceeds threshold"""
        # Setup mocks for non-dry run mode
        mock_settings.DRY_RUN = False
        mock_settings.PANIC_STOP = False
        mock_settings.ADMIN_TOKEN = "test_admin_token"
        mock_settings.BOT_TOKEN = "test_bot_token"
        mock_settings.REPORT_CATEGORY_DEFAULT = "spam"
        mock_settings.FORWARD_REMOTE_REPORTS = False
        mock_settings.POLICY_VERSION = "1.0"
        mock_settings.MAX_STATUSES_TO_FETCH = 100

        # Mock rule service to return high score
        mock_rule_service.evaluate_account.return_value = [
            Violation(
                rule_name="high_risk_rule",
                rule_type="t",
                score=2.5,
                evidence={"matched_terms": [], "matched_status_ids": [], "metrics": {}},
                actions=[{"type": "report"}],
            )
        ]
        mock_rule_service.get_active_rules.return_value = (
            [],
            {"report_threshold": 1.0},
            "test_sha",
        )

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Mock scanning database session
        mock_scanning_session = MagicMock()
        mock_scanning_db.return_value.__enter__.return_value = mock_scanning_session
        mock_scanning_session.query.return_value.filter.return_value.first.return_value = None

        # Mock admin client
        mock_admin = MagicMock()
        mock_admin_client.return_value = mock_admin
        mock_admin.get_account_statuses.return_value = [{"id": "status1", "content": "suspicious content"}]

        # Mock bot client
        mock_client = MagicMock()
        mock_bot_client.return_value = mock_client
        mock_client.create_report.return_value = {"id": "report_789"}

        # Test data
        payload = {
            "account": {
                "id": "123456",
                "acct": "suspicious@example.com",
                "domain": "example.com",
            },
            "statuses": [{"id": "status1", "content": "suspicious content"}],
        }

        # Call the function
        result = analyze_and_maybe_report(payload)

        # Should create a report since score (2.5) > threshold (1.0)
        self.assertIsNotNone(result)
        mock_client.create_report.assert_called_once()

    @patch("app.tasks.jobs.SessionLocal")
    @patch("app.tasks.jobs.rule_service")
    @patch("app.tasks.jobs.get_settings")
    def test_analyze_and_maybe_report_no_report_low_score(self, mock_settings, mock_rule_service, mock_db):
        """Test that no report is created when score is below threshold"""
        # Setup mocks
        mock_settings.return_value.DRY_RUN = False
        mock_settings.return_value.PANIC_STOP = False

        # Mock rule service to return low score
        mock_rule_service.evaluate_account.return_value = [
            Violation(
                rule_name="low_risk_rule",
                rule_type="t",
                score=0.5,
                evidence={"matched_terms": [], "matched_status_ids": [], "metrics": {}},
                actions=[{"type": "report"}],
            )
        ]
        mock_rule_service.get_active_rules.return_value = (
            [],
            {"report_threshold": 1.0},
            "test_sha",
        )

        mock_db_session = MagicMock()
        mock_db.return_value.__enter__.return_value = mock_db_session

        # Test data
        payload = {
            "account": {
                "id": "123456",
                "acct": "normal@example.com",
                "domain": "example.com",
            },
            "statuses": [{"id": "status1", "content": "normal content"}],
        }

        # Call the function
        result = analyze_and_maybe_report(payload)

        # Should not create a report since score (0.5) < threshold (1.0)
        self.assertIsNone(result)
        # No report should be created, but analysis should be recorded

    @patch("app.tasks.jobs._poll_accounts")
    def test_poll_admin_accounts_wrapper(self, mock_poll):
        """Ensure poll_admin_accounts calls helper."""
        poll_admin_accounts()
        mock_poll.assert_called_once_with("remote", CURSOR_NAME)

    @patch("app.tasks.jobs._poll_accounts")
    def test_poll_admin_accounts_local_wrapper(self, mock_poll):
        """Ensure local poll uses correct cursor."""
        poll_admin_accounts_local()
        mock_poll.assert_called_once_with("local", CURSOR_NAME_LOCAL)

    @patch("app.tasks.jobs.analyze_and_maybe_report")
    @patch("app.tasks.jobs._persist_account")
    @patch("app.tasks.jobs.cursor_lag_pages")
    @patch("app.tasks.jobs.SessionLocal")
    @patch("app.tasks.jobs.EnhancedScanningSystem")
    def test_poll_accounts_metrics(self, mock_scanner, mock_session, mock_metric, mock_persist, mock_analyze):
        """Record metrics during polling."""
        jobs.settings.MAX_PAGES_PER_POLL = 1
        jobs.settings.BATCH_SIZE = 1
        db_session = MagicMock()
        exec_result = MagicMock()
        exec_result.scalar.return_value = None
        db_session.execute.return_value = exec_result
        mock_session.return_value.__enter__.return_value = db_session
        scanner = mock_scanner.return_value
        scanner.start_scan_session.return_value = "s"
        scanner.get_next_accounts_to_scan.return_value = ([], None)
        metric = MagicMock()
        mock_metric.labels.return_value = metric
        with patch("app.tasks.jobs._should_pause", return_value=False):
            for origin, cursor in [
                ("remote", CURSOR_NAME),
                ("local", CURSOR_NAME_LOCAL),
            ]:
                _poll_accounts(origin, cursor)
        scanner.get_next_accounts_to_scan.assert_has_calls(
            [
                call("remote", limit=jobs.settings.BATCH_SIZE, cursor=None),
                call("local", limit=jobs.settings.BATCH_SIZE, cursor=None),
            ]
        )
        mock_metric.labels.assert_has_calls([call(cursor=CURSOR_NAME), call(cursor=CURSOR_NAME_LOCAL)])
        self.assertEqual(metric.set.call_count, 2)


if __name__ == "__main__":
    unittest.main()
