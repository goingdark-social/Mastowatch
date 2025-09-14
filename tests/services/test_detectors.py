"""Test cases for detector modules."""

import unittest
from hashlib import sha256
from unittest.mock import Mock
from datetime import datetime, timedelta

from app.schemas import Violation
from app.services.detectors.behavioral_detector import BehavioralDetector
from app.services.detectors.keyword_detector import KeywordDetector
from app.services.detectors.media_detector import MediaDetector
from app.services.detectors.regex_detector import RegexDetector


class TestRegexDetector(unittest.TestCase):
    """Test suite for RegexDetector."""

    def setUp(self):
        """Set up test environment."""
        self.detector = RegexDetector()

    def test_evaluate_username_match(self):
        """Test regex matching in username field."""
        rule = Mock()
        rule.pattern = r"crypto|bitcoin|nft"
        rule.trigger_threshold = 1.0
        rule.name = "crypto_username_rule"
        rule.detector_type = "regex"
        rule.weight = 1.5

        account_data = {
            "username": "crypto_trader",
            "acct": "crypto_trader@example.com",
            "note": "Regular trading account",
        }
        statuses = []

        violations = self.detector.evaluate(rule, account_data, statuses)

        self.assertEqual(len(violations), 1)
        self.assertIsInstance(violations[0], Violation)
        self.assertEqual(violations[0].rule_name, "crypto_username_rule")
        self.assertEqual(violations[0].score, 1.5)
        self.assertIn("matched_pattern", violations[0].evidence)

    def test_evaluate_bio_match(self):
        """Test regex matching in bio/note field."""
        rule = Mock()
        rule.pattern = r"casino|gambling|poker"
        rule.trigger_threshold = 1.0
        rule.name = "gambling_bio_rule"
        rule.detector_type = "regex"
        rule.weight = 2.0

        account_data = {
            "username": "normal_user",
            "acct": "normal_user@example.com",
            "note": "I love playing poker and casino games!",
        }
        statuses = []

        violations = self.detector.evaluate(rule, account_data, statuses)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].score, 2.0)
        self.assertIn("poker", violations[0].evidence["matched_pattern"])

    def test_evaluate_status_content_match(self):
        """Test regex matching in status content."""
        rule = Mock()
        rule.pattern = r"buy now|limited time|act fast"
        rule.trigger_threshold = 1.0
        rule.name = "spam_content_rule"
        rule.detector_type = "regex"
        rule.weight = 1.0

        account_data = {"username": "user", "note": "Normal bio"}
        statuses = [
            {"content": "Check out this amazing deal - buy now!", "id": "1"},
            {"content": "Regular post about daily life", "id": "2"},
            {"content": "Limited time offer - act fast!", "id": "3"},
        ]

        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 2)
        for violation in violations:
            self.assertEqual(violation.score, 1.0)

    def test_evaluate_no_match(self):
        """Test when regex pattern doesn't match anything."""
        rule = Mock()
        rule.pattern = r"nonexistent_pattern_xyz"
        rule.trigger_threshold = 1.0
        rule.name = "no_match_rule"
        rule.detector_type = "regex"
        rule.weight = 1.0

        account_data = {"username": "user", "note": "Normal content"}
        statuses = [{"content": "Regular status", "id": "1"}]

        violations = self.detector.evaluate(rule, account_data, statuses)

        self.assertEqual(len(violations), 0)

    def test_evaluate_case_insensitive(self):
        """Test that regex matching is case-insensitive."""
        rule = Mock()
        rule.pattern = r"URGENT|urgent|Urgent"
        rule.trigger_threshold = 1.0
        rule.name = "case_test_rule"
        rule.detector_type = "regex"
        rule.weight = 1.0

        account_data = {"username": "user", "note": "This is URGENT business"}
        statuses = [{"content": "urgent message here", "id": "1"}]

        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 2)


class TestKeywordDetector(unittest.TestCase):
    """Test suite for KeywordDetector."""

    def setUp(self):
        """Set up test environment."""
        self.detector = KeywordDetector()

    def test_evaluate_comma_separated_keywords(self):
        """Test keyword detection with comma-separated list."""
        rule = Mock()
        rule.pattern = "casino,adult,pills,viagra"
        rule.trigger_threshold = 1.0
        rule.name = "spam_keywords_rule"
        rule.detector_type = "keyword"
        rule.weight = 2.0

        account_data = {"username": "user", "note": "Visit our casino for adult entertainment"}
        statuses = [{"content": "Get cheap viagra pills online", "id": "1"}]

        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertGreater(len(violations), 0)
        for violation in violations:
            self.assertEqual(violation.score, 2.0)
            self.assertIn("matched_keywords", violation.evidence)

    def test_evaluate_single_keyword(self):
        """Test keyword detection with single keyword."""
        rule = Mock()
        rule.pattern = "scam"
        rule.trigger_threshold = 1.0
        rule.name = "scam_keyword_rule"
        rule.detector_type = "keyword"
        rule.weight = 3.0

        account_data = {"username": "user", "note": "This is a scam warning"}
        statuses = []

        violations = self.detector.evaluate(rule, account_data, statuses)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].score, 3.0)
        self.assertIn("scam", violations[0].evidence["matched_keywords"])

    def test_evaluate_partial_word_match(self):
        """Test that keywords match as substrings."""
        rule = Mock()
        rule.pattern = "free"
        rule.trigger_threshold = 1.0
        rule.name = "free_keyword_rule"
        rule.detector_type = "keyword"
        rule.weight = 1.0

        account_data = {"username": "user", "note": "Enjoy freedom of speech"}
        statuses = []

        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)

    def test_evaluate_no_keyword_match(self):
        """Test when no keywords are found."""
        rule = Mock()
        rule.pattern = "nonexistent,impossible,notfound"
        rule.trigger_threshold = 1.0
        rule.name = "no_keywords_rule"
        rule.detector_type = "keyword"
        rule.weight = 1.0

        account_data = {"username": "user", "note": "Normal content here"}
        statuses = [{"content": "Regular status update", "id": "1"}]

        violations = self.detector.evaluate(rule, account_data, statuses)

        self.assertEqual(len(violations), 0)


class TestBehavioralDetector(unittest.TestCase):
    """Test suite for BehavioralDetector."""

    def setUp(self):
        """Set up test environment."""
        self.detector = BehavioralDetector()

    def test_automation_disclosure_non_bot(self):
        """Flag non-bot accounts with templated posts."""
        rule = Mock()
        rule.pattern = "automation_disclosure"
        rule.trigger_threshold = 1.0
        rule.name = "automation_disclosure_rule"
        rule.detector_type = "behavioral"
        rule.weight = 1.0
        base_time = datetime.utcnow()
        statuses = []
        for i in range(20):
            content = f"Scheduled update {i}" if i % 2 == 0 else "Random"
            created_at = (base_time - timedelta(minutes=i)).isoformat()
            statuses.append({"id": str(i), "content": content, "created_at": created_at, "visibility": "public"})
        account_data = {"mastodon_account_id": "1", "bot": False}
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)
        self.assertIn("automation_percentage", violations[0].evidence.metrics)

    def test_automation_disclosure_bot_rate(self):
        """Flag bots with high public posting rates."""
        rule = Mock()
        rule.pattern = "automation_disclosure"
        rule.trigger_threshold = 1.0
        rule.name = "automation_disclosure_rule"
        rule.detector_type = "behavioral"
        rule.weight = 1.0
        base_time = datetime.utcnow()
        statuses = []
        for i in range(5):
            created_at = (base_time - timedelta(minutes=i)).isoformat()
            statuses.append({"id": str(i), "content": f"Update {i}", "created_at": created_at, "visibility": "public"})
        account_data = {"mastodon_account_id": "2", "bot": True}
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)
        self.assertIn("hourly_rate", violations[0].evidence.metrics)

    def test_link_spam_single_domain(self):
        """Detect link spam with single domain."""
        rule = Mock()
        rule.pattern = "link_spam"
        rule.trigger_threshold = 1.0
        rule.name = "link_spam_rule"
        rule.detector_type = "behavioral"
        rule.weight = 1.0
        base_time = datetime.utcnow()
        statuses = []
        for i in range(20):
            created_at = (base_time - timedelta(minutes=i)).isoformat()
            statuses.append(
                {
                    "id": str(i),
                    "content": f"Check this out http://example.com/post/{i}",
                    "created_at": created_at,
                    "visibility": "public",
                }
            )
        account_data = {"mastodon_account_id": "3", "bot": False}
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)
        self.assertIn("domain_distribution", violations[0].evidence.metrics)


class TestMediaDetector(unittest.TestCase):
    """Test suite for MediaDetector."""

    def setUp(self):
        """Initialize detector."""
        self.detector = MediaDetector()

    def test_alt_text_match(self):
        """Detect pattern in attachment alt text."""
        rule = Mock()
        rule.pattern = "kitten"
        rule.name = "alt_text_rule"
        rule.detector_type = "media"
        rule.weight = 1.0
        account_data = {}
        statuses = [
            {
                "id": "1",
                "media_attachments": [{"description": "cute kitten", "mime_type": "image/jpeg", "url": "http://a"}],
            }
        ]
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)

    def test_mime_type_match(self):
        """Detect pattern in MIME type."""
        rule = Mock()
        rule.pattern = "image/png"
        rule.name = "mime_rule"
        rule.detector_type = "media"
        rule.weight = 1.0
        account_data = {}
        statuses = [
            {
                "id": "1",
                "media_attachments": [{"description": "", "mime_type": "image/png", "url": "http://b"}],
            }
        ]
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)

    def test_hash_match(self):
        """Detect pattern in URL hash."""
        url = "http://example.com/image.png"
        pattern = sha256(url.encode()).hexdigest()
        rule = Mock()
        rule.pattern = pattern
        rule.name = "hash_rule"
        rule.detector_type = "media"
        rule.weight = 1.0
        account_data = {}
        statuses = [
            {
                "id": "1",
                "media_attachments": [{"description": "", "mime_type": "image/png", "url": url}],
            }
        ]
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)


if __name__ == "__main__":
    unittest.main()
