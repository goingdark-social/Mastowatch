"""Test cases for detector modules."""

import unittest
from datetime import datetime, timedelta
from hashlib import sha256
from unittest.mock import Mock, patch

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
        rule.target_fields = None  # Default to all fields

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

    def test_evaluate_with_target_fields(self):
        """Test regex matching with specific target fields."""
        rule = Mock()
        rule.pattern = r"spam"
        rule.trigger_threshold = 1.0
        rule.name = "spam_rule"
        rule.detector_type = "regex"
        rule.weight = 1.0
        rule.target_fields = ["username"]  # Only check username

        account_data = {
            "username": "spam_account",
            "display_name": "Normal Name",
            "note": "This bio contains spam word",
        }
        statuses = []

        violations = self.detector.evaluate(rule, account_data, statuses)

        # Should only match username, not bio
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].evidence["metrics"]["field"], "username")

    def test_evaluate_bio_match(self):
        """Test regex matching in bio/note field."""
        rule = Mock()
        rule.pattern = r"casino|gambling|poker"
        rule.trigger_threshold = 1.0
        rule.name = "gambling_bio_rule"
        rule.detector_type = "regex"
        rule.weight = 2.0
        rule.target_fields = None

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
        rule.target_fields = None

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
        rule.target_fields = None

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
        rule.target_fields = None

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
        rule.target_fields = None  # Default to all
        rule.match_options = None  # Default options

        account_data = {"username": "user", "note": "Visit our casino for adult entertainment"}
        statuses = [{"content": "Get cheap viagra pills online", "id": "1"}]

        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertGreater(len(violations), 0)
        for violation in violations:
            self.assertEqual(violation.score, 2.0)
            self.assertIn("matched_keywords", violation.evidence)

    def test_evaluate_with_word_boundaries(self):
        """Test keyword detection with word boundaries enabled."""
        rule = Mock()
        rule.pattern = "spam"
        rule.trigger_threshold = 1.0
        rule.name = "spam_keyword_rule"
        rule.detector_type = "keyword"
        rule.weight = 1.0
        rule.target_fields = None
        rule.match_options = {"case_sensitive": False, "word_boundaries": True}

        # "spam" as whole word should match
        account_data = {"username": "user", "note": "This is spam content"}
        statuses = []
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)

        # "spam" in "spammer" should NOT match with word boundaries
        account_data = {"username": "user", "note": "This is spammer content"}
        statuses = []
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 0)

    def test_evaluate_without_word_boundaries(self):
        """Test keyword detection with word boundaries disabled."""
        rule = Mock()
        rule.pattern = "spam"
        rule.trigger_threshold = 1.0
        rule.name = "spam_keyword_rule"
        rule.detector_type = "keyword"
        rule.weight = 1.0
        rule.target_fields = None
        rule.match_options = {"case_sensitive": False, "word_boundaries": False}

        # Should match "spam" in "spammer"
        account_data = {"username": "user", "note": "This is spammer content"}
        statuses = []
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)

    def test_evaluate_with_target_fields_username_only(self):
        """Test keyword detection targeting only username."""
        rule = Mock()
        rule.pattern = "spam"
        rule.trigger_threshold = 1.0
        rule.name = "spam_keyword_rule"
        rule.detector_type = "keyword"
        rule.weight = 1.0
        rule.target_fields = ["username"]
        rule.match_options = {"case_sensitive": False, "word_boundaries": False}

        # "spam" in username should match
        account_data = {"username": "spam_account", "note": "Normal bio"}
        statuses = []
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].evidence["metrics"]["field"], "username")

        # "spam" only in bio should NOT match (username not targeted)
        account_data = {"username": "normal_user", "note": "spam content"}
        statuses = []
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 0)

    def test_evaluate_case_sensitive(self):
        """Test case-sensitive keyword matching."""
        rule = Mock()
        rule.pattern = "SPAM"
        rule.trigger_threshold = 1.0
        rule.name = "spam_keyword_rule"
        rule.detector_type = "keyword"
        rule.weight = 1.0
        rule.target_fields = None
        rule.match_options = {"case_sensitive": True, "word_boundaries": False}

        # Exact case should match
        account_data = {"username": "user", "note": "This is SPAM"}
        statuses = []
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 1)

        # Different case should NOT match
        account_data = {"username": "user", "note": "This is spam"}
        statuses = []
        violations = self.detector.evaluate(rule, account_data, statuses)
        self.assertEqual(len(violations), 0)

    def test_evaluate_single_keyword(self):
        """Test keyword detection with single keyword."""
        rule = Mock()
        rule.pattern = "scam"
        rule.trigger_threshold = 1.0
        rule.name = "scam_keyword_rule"
        rule.detector_type = "keyword"
        rule.weight = 3.0
        rule.target_fields = None
        rule.match_options = None

        account_data = {"username": "user", "note": "This is a scam warning"}
        statuses = []

        violations = self.detector.evaluate(rule, account_data, statuses)

        self.assertEqual(len(violations), 1)
        self.assertEqual(violations[0].score, 3.0)
        self.assertIn("scam", violations[0].evidence["matched_keywords"])

    def test_evaluate_partial_word_match(self):
        """Test that keywords match as substrings when word_boundaries is False."""
        rule = Mock()
        rule.pattern = "free"
        rule.trigger_threshold = 1.0
        rule.name = "free_keyword_rule"
        rule.detector_type = "keyword"
        rule.weight = 1.0
        rule.target_fields = None
        rule.match_options = {"case_sensitive": False, "word_boundaries": False}

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
        rule.target_fields = None
        rule.match_options = None

        account_data = {"username": "user", "note": "Normal content here"}
        statuses = [{"content": "Regular status update", "id": "1"}]

        violations = self.detector.evaluate(rule, account_data, statuses)

        self.assertEqual(len(violations), 0)


class TestBehavioralDetector(unittest.TestCase):
    """Test suite for BehavioralDetector."""

    def setUp(self):
        """Set up test environment."""
        self.detector = BehavioralDetector()

        # Mock database session and queries
        self.session_patcher = patch("app.services.detectors.behavioral_detector.Session")
        self.mock_session_class = self.session_patcher.start()
        self.mock_session = Mock()
        self.mock_session_class.return_value.__enter__.return_value = self.mock_session

        # Mock query chain
        self.mock_query = Mock()
        self.mock_session.query.return_value = self.mock_query
        self.mock_query.filter.return_value = self.mock_query
        self.mock_query.order_by.return_value = self.mock_query
        self.mock_query.limit.return_value = self.mock_query
        # Default count for database interactions
        self.mock_query.count.return_value = 0
        self.mock_query.all.return_value = []

    def tearDown(self):
        """Clean up test environment."""
        self.session_patcher.stop()

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
