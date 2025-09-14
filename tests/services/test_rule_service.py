"""Test cases for rule evaluation functionality."""

import os
import tempfile
import unittest
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Rule
from app.services.rule_service import RuleService


class TestRuleService(unittest.TestCase):
    """Test class for rule evaluation using database-driven rules."""

    def setUp(self):
        """Set up a clean test database for each test."""
        # Create a temporary in-memory SQLite database
        self.test_db = tempfile.NamedTemporaryFile(delete=False, suffix=".db")
        self.test_db_url = f"sqlite:///{self.test_db.name}"

        # Create engine and session factory
        self.engine = create_engine(self.test_db_url, echo=False)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

        # Create a test rule service instance with a fresh cache
        self.rule_service = RuleService(cache_ttl_seconds=1)

        # Mock the global SessionLocal to use our test database
        self.db_patcher = patch("app.services.rule_service.SessionLocal", self.SessionLocal)
        self.db_patcher.start()

        # Create test rules in the database
        self._create_test_rules()

    def tearDown(self):
        """Clean up after each test."""
        self.db_patcher.stop()
        self.engine.dispose()
        os.unlink(self.test_db.name)

    def _create_test_rules(self):
        """Create sample rules for testing."""
        with self.SessionLocal() as session:
            # Rule 1: Regex detector for crypto-related usernames
            crypto_rule = Rule(
                name="crypto_username_test",
                detector_type="regex",
                pattern="crypto|bitcoin|nft",
                weight=1.5,
                action_type="report",
                trigger_threshold=1.0,
                enabled=True,
                description="Detects crypto-related usernames",
            )
            session.add(crypto_rule)

            # Rule 2: Keyword detector for spam content
            spam_rule = Rule(
                name="spam_keywords_test",
                detector_type="keyword",
                pattern="casino,adult,pills",
                weight=2.0,
                action_type="report",
                trigger_threshold=1.5,
                enabled=True,
                description="Detects spam keywords",
            )
            session.add(spam_rule)

            # Rule 3: Disabled rule that shouldn't trigger
            disabled_rule = Rule(
                name="disabled_rule_test",
                detector_type="regex",
                pattern="test_disabled",
                weight=5.0,
                action_type="suspend",
                trigger_threshold=1.0,
                enabled=False,
                description="Disabled rule for testing",
            )
            session.add(disabled_rule)

            session.commit()

    def test_get_active_rules(self):
        """Test getting active rules from database."""
        rules, config, ruleset_sha = self.rule_service.get_active_rules()

        # Should have 2 enabled rules (crypto and spam)
        self.assertEqual(len(rules), 2)

        # Verify rule names
        rule_names = [rule.name for rule in rules]
        self.assertIn("crypto_username_test", rule_names)
        self.assertIn("spam_keywords_test", rule_names)
        self.assertNotIn("disabled_rule_test", rule_names)

        # Verify config structure
        self.assertIn("report_threshold", config)
        self.assertEqual(config["report_threshold"], 1.0)  # Default value

        # Verify SHA is generated
        self.assertIsInstance(ruleset_sha, str)
        self.assertEqual(len(ruleset_sha), 64)  # SHA256 length

    def test_evaluate_account_new_interface(self):
        """Test account evaluation using new evaluate_account interface."""
        account = {
            "acct": "test@example.com",
            "username": "test_user",
            "note": "Normal account",
        }

        statuses = []

        # Mock detectors to return no violations
        with patch.object(self.rule_service.detectors["regex"], "evaluate") as mock_regex:
            with patch.object(self.rule_service.detectors["keyword"], "evaluate") as mock_keyword:
                mock_regex.return_value = []
                mock_keyword.return_value = []

                violations = self.rule_service.evaluate_account(account, statuses)

                # Should have no violations
                self.assertEqual(len(violations), 0)

    def test_evaluate_account_compound_and(self):
        account = {"acct": "compound@example.com", "username": "spamuser", "note": "bio"}
        statuses = [{"id": "1", "content": "lottery games"}]  # Changed from "casino" to "lottery" to avoid existing rule
        self.rule_service.create_rule(
            name="compound_rule",
            detector_type="regex",
            pattern="spam",
            boolean_operator="AND",
            secondary_pattern="lottery",  # Changed to match new content
            weight=1.0,
            action_type="report",
            trigger_threshold=1.0,
        )
        self.rule_service.invalidate_cache()
        violations = self.rule_service.evaluate_account(account, statuses)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].actions[0]["type"], "report")

    def test_cache_invalidation(self):
        """Test that cache invalidation works correctly."""
        # Get rules to populate cache
        rules1, _, sha1 = self.rule_service.get_active_rules()

        # Add a new rule to database
        with self.SessionLocal() as session:
            new_rule = Rule(
                name="new_test_rule",
                detector_type="regex",
                pattern="new_pattern",
                weight=1.0,
                action_type="report",
                trigger_threshold=1.0,
                enabled=True,
            )
            session.add(new_rule)
            session.commit()

        # Without cache invalidation, should still get old rules
        rules2, _, sha2 = self.rule_service.get_active_rules()
        self.assertEqual(len(rules2), 2)  # Still old count
        self.assertEqual(sha1, sha2)  # Same SHA

        # After invalidation, should get updated rules
        self.rule_service.invalidate_cache()
        rules3, _, sha3 = self.rule_service.get_active_rules()
        self.assertEqual(len(rules3), 3)  # New count
        self.assertNotEqual(sha1, sha3)  # Different SHA

    def test_rule_crud_operations(self):
        """Test CRUD operations for rules."""
        # Test create
        new_rule = self.rule_service.create_rule(
            name="test_crud_rule",
            detector_type="regex",
            pattern="test_pattern",
            weight=1.0,
            action_type="report",
            trigger_threshold=1.0,
            description="Test CRUD rule",
        )

        self.assertIsNotNone(new_rule.id)
        self.assertEqual(new_rule.name, "test_crud_rule")

        # Test read
        retrieved_rule = self.rule_service.get_rule_by_id(new_rule.id)
        self.assertIsNotNone(retrieved_rule)
        self.assertEqual(retrieved_rule.name, "test_crud_rule")

        # Test update
        updated_rule = self.rule_service.update_rule(new_rule.id, weight=2.0, description="Updated description")
        self.assertEqual(updated_rule.weight, 2.0)
        self.assertEqual(updated_rule.description, "Updated description")

        # Test delete
        deleted = self.rule_service.delete_rule(new_rule.id)
        self.assertTrue(deleted)

        # Verify deletion
        deleted_rule = self.rule_service.get_rule_by_id(new_rule.id)
        self.assertIsNone(deleted_rule)

    def test_rule_statistics(self):
        """Test rule statistics generation."""
        stats = self.rule_service.get_rule_statistics()

        self.assertIn("total_rules", stats)
        self.assertIn("enabled_rules", stats)
        self.assertIn("disabled_rules", stats)
        self.assertIn("cache_status", stats)

        self.assertEqual(stats["total_rules"], 3)
        self.assertEqual(stats["enabled_rules"], 2)
        self.assertEqual(stats["disabled_rules"], 1)

    def test_rule_cache_ttl_override(self):
        from app.services import rule_service as rs_module

        with patch.object(rs_module.settings, "RULE_CACHE_TTL", 5):
            service = rs_module.RuleService()
            # Mock the database session to return empty results
            with patch.object(rs_module, "SessionLocal") as mock_session_local:
                mock_session = mock_session_local.return_value.__enter__.return_value
                mock_session.query.return_value.filter.return_value.all.return_value = []
                mock_session.execute.return_value.scalar.return_value = None
                
                service.get_active_rules()
                self.assertEqual(service._cache.ttl_seconds, 5)


if __name__ == "__main__":
    unittest.main()
