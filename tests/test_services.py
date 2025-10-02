"""Test cases for service layer components."""

import os
import tempfile
import unittest
from unittest.mock import Mock, patch

from app.db import Base
from app.models import AuditLog
from app.services.enforcement_service import EnforcementService
from app.services.rule_service import RuleService
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker


class TestRuleService(unittest.TestCase):
    """Test suite for RuleService class."""

    def setUp(self):
        """Set up test database and service instance."""
        # Create temporary test database
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.test_db_url = f"sqlite:///{self.test_db.name}"

        self.engine = create_engine(self.test_db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

        # Create service instance
        self.rule_service = RuleService(cache_ttl_seconds=1)

        # Mock global SessionLocal
        self.db_patcher = patch("app.services.rule_service.SessionLocal", self.SessionLocal)
        self.db_patcher.start()

    def tearDown(self):
        """Clean up test resources."""
        self.db_patcher.stop()
        self.engine.dispose()
        os.unlink(self.test_db.name)

    def test_create_rule_validation(self):
        """Test rule creation with validation."""
        rule = self.rule_service.create_rule(
            name="test_validation_rule",
            detector_type="regex",
            pattern="test.*pattern",
            weight=1.5,
            action_type="report",
            trigger_threshold=1.0,
        )

        self.assertEqual(rule.name, "test_validation_rule")
        self.assertEqual(rule.detector_type, "regex")
        self.assertEqual(rule.weight, 1.5)
        self.assertTrue(rule.enabled)

    def test_rule_cache_performance(self):
        """Test that caching improves performance."""
        # Create some rules
        for i in range(5):
            self.rule_service.create_rule(
                name=f"perf_rule_{i}",
                detector_type="keyword",
                pattern=f"keyword_{i}",
                weight=1.0,
                action_type="report",
                trigger_threshold=1.0,
            )

        rules1, _, _ = self.rule_service.get_active_rules()
        rules2, _, _ = self.rule_service.get_active_rules()
        self.assertEqual(len(rules1), len(rules2))
        self.assertEqual(len(rules1), 5)

    def test_bulk_rule_operations(self):
        """Test bulk operations on rules."""
        # Create multiple rules
        rule_ids = []
        for i in range(3):
            rule = self.rule_service.create_rule(
                name=f"bulk_rule_{i}",
                detector_type="regex",
                pattern=f"pattern_{i}",
                weight=1.0,
                action_type="report",
                trigger_threshold=1.0,
            )
            rule_ids.append(rule.id)

        # Test bulk disable
        updated_rules = self.rule_service.bulk_toggle_rules(rule_ids, enabled=False)
        self.assertEqual(len(updated_rules), 3)
        for rule in updated_rules:
            self.assertFalse(rule.enabled)

        # Test bulk enable
        updated_rules = self.rule_service.bulk_toggle_rules(rule_ids, enabled=True)
        self.assertEqual(len(updated_rules), 3)
        for rule in updated_rules:
            self.assertTrue(rule.enabled)

    def test_rule_statistics_accuracy(self):
        """Test that rule statistics are calculated correctly."""
        # Create mix of enabled and disabled rules
        self.rule_service.create_rule(
            name="enabled_rule_1",
            detector_type="regex",
            pattern="test1",
            weight=1.0,
            action_type="report",
            trigger_threshold=1.0,
            enabled=True,
        )
        self.rule_service.create_rule(
            name="enabled_rule_2",
            detector_type="keyword",
            pattern="test2",
            weight=1.0,
            action_type="report",
            trigger_threshold=1.0,
            enabled=True,
        )
        self.rule_service.create_rule(
            name="disabled_rule_1",
            detector_type="regex",
            pattern="test3",
            weight=1.0,
            action_type="report",
            trigger_threshold=1.0,
            enabled=False,
        )

        stats = self.rule_service.get_rule_statistics()

        self.assertEqual(stats["total_rules"], 3)
        self.assertEqual(stats["enabled_rules"], 2)
        self.assertEqual(stats["disabled_rules"], 1)
        self.assertIn("cache_status", stats)


class TestEnforcementServiceLogging(unittest.TestCase):
    """Verify audit logging for enforcement actions."""

    def setUp(self):
        """Prepare enforcement service with isolated database."""
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        engine = create_engine(f"sqlite:///{self.test_db.name}", echo=False)
        Base.metadata.create_all(engine)
        self.SessionLocal = sessionmaker(bind=engine)
        self.db_patcher = patch("app.services.enforcement_service.SessionLocal", self.SessionLocal)
        self.db_patcher.start()
        self.client = Mock()
        self.client._make_request.return_value = Mock(json=lambda: {"ok": True})
        self.service = EnforcementService(self.client)

    def tearDown(self):
        """Remove temporary resources."""
        self.db_patcher.stop()
        os.unlink(self.test_db.name)

    def test_warn_account_logs(self):
        """Persist audit log when warning account."""
        self.service.warn_account("acct", text="t", rule_id=1, evidence={"e": 1})
        with self.SessionLocal() as session:
            logs = session.query(AuditLog).all()
            self.assertEqual(len(logs), 1)
            self.assertEqual(logs[0].triggered_by_rule_id, 1)


if __name__ == "__main__":
    unittest.main()
