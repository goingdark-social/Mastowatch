import os
import sys
import unittest
from pathlib import Path

# Add the app directory to the path so we can import the app modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.config import Settings


class TestConfig(unittest.TestCase):
    def setUp(self):
        """Set up test environment variables"""
        self.test_env = {
            "INSTANCE_BASE": "https://test.mastodon.social",
            "MASTODON_CLIENT_SECRET": "test_MASTODON_CLIENT_SECRET",
            "MASTODON_CLIENT_SECRET": "test_MASTODON_CLIENT_SECRET",
            "DATABASE_URL": "postgresql://test:test@localhost:5432/test",
            "REDIS_URL": "redis://localhost:6379/1",
            "UI_ORIGIN": "http://localhost:3000",
        }

        # Store original values to restore later
        self.original_env = {}
        for key in self.test_env:
            self.original_env[key] = os.environ.get(key)
            os.environ[key] = self.test_env[key]

    def tearDown(self):
        """Restore original environment variables"""
        for key, value in self.original_env.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value

    def test_required_settings_load(self):
        """Test that required settings are loaded properly"""
        settings = Settings()

        self.assertEqual(
            str(settings.INSTANCE_BASE).rstrip("/"),
            self.test_env["INSTANCE_BASE"],
        )
        self.assertEqual(settings.MASTODON_CLIENT_SECRET, self.test_env["MASTODON_CLIENT_SECRET"])
        self.assertEqual(settings.MASTODON_CLIENT_SECRET, self.test_env["MASTODON_CLIENT_SECRET"])
        self.assertEqual(settings.DATABASE_URL, self.test_env["DATABASE_URL"])
        self.assertEqual(settings.REDIS_URL, self.test_env["REDIS_URL"])

    def test_default_values(self):
        """Test that default values are set correctly"""
        settings = Settings()

        self.assertTrue(settings.DRY_RUN)  # Default should be True
        self.assertEqual(settings.MAX_PAGES_PER_POLL, 3)
        self.assertEqual(settings.MAX_STATUSES_TO_FETCH, 5)
        self.assertEqual(settings.REPORT_CATEGORY_DEFAULT, "spam")
        self.assertFalse(settings.FORWARD_REMOTE_REPORTS)
        self.assertFalse(settings.PANIC_STOP)

    def test_environment_override(self):
        """Test that environment variables override defaults"""
        os.environ["DRY_RUN"] = "false"
        os.environ["MAX_PAGES_PER_POLL"] = "5"
        os.environ["MAX_STATUSES_TO_FETCH"] = "200"
        os.environ["REPORT_CATEGORY_DEFAULT"] = "violation"

        settings = Settings()

        self.assertFalse(settings.DRY_RUN)
        self.assertEqual(settings.MAX_PAGES_PER_POLL, 5)
        self.assertEqual(settings.MAX_STATUSES_TO_FETCH, 200)
        self.assertEqual(settings.REPORT_CATEGORY_DEFAULT, "violation")

        # Clean up
        del os.environ["DRY_RUN"]
        del os.environ["MAX_PAGES_PER_POLL"]
        del os.environ["MAX_STATUSES_TO_FETCH"]
        del os.environ["REPORT_CATEGORY_DEFAULT"]

    def test_cors_origins_parsing(self):
        """Test that CORS_ORIGINS is parsed as a list"""
        os.environ["CORS_ORIGINS"] = '["http://localhost:3000", "https://app.example.com"]'

        settings = Settings()

        self.assertIsInstance(settings.CORS_ORIGINS, list)
        self.assertEqual(len(settings.CORS_ORIGINS), 2)
        self.assertIn("http://localhost:3000", settings.CORS_ORIGINS)

        # Clean up
        del os.environ["CORS_ORIGINS"]

    def test_missing_required_field(self):
        """Test that missing required fields raise validation errors"""
        # Remove a required field
        del os.environ["MASTODON_CLIENT_SECRET"]

        from pydantic import ValidationError

        with self.assertRaises(ValidationError):
            # Prevent .env file loading by passing _env_file=None
            Settings(_env_file=None)

        # Restore for tearDown
        os.environ["MASTODON_CLIENT_SECRET"] = self.test_env["MASTODON_CLIENT_SECRET"]


if __name__ == "__main__":
    unittest.main()
