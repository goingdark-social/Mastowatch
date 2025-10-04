"""Tests for mastodon.py integration via MastodonService."""

import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

# Set test environment before any imports
os.environ.update(
    {
        "SKIP_STARTUP_VALIDATION": "1",
        "INSTANCE_BASE": "https://test.mastodon.social",
        "ADMIN_TOKEN": "test_admin_token_123456789",
        "BOT_TOKEN": "test_bot_token_123456789",
        "OAUTH_CLIENT_ID": "test_client_id",
        "OAUTH_CLIENT_SECRET": "test_client_secret",
        "DATABASE_URL": "postgresql+psycopg://test:test@localhost:5433/mastowatch_test",
        "REDIS_URL": "redis://localhost:6380/1",
        "UI_ORIGIN": "http://localhost:3000",
    }
)

# Add backend directory to path
backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


class TestMastodonService(unittest.TestCase):
    """Test MastodonService wrapper for mastodon.py."""

    def setUp(self):
        """Set up test fixtures."""
        from app.services.mastodon_service import MastodonService

        self.service = MastodonService()

    def test_service_initialization(self):
        """Test that service initializes correctly."""
        self.assertIsNotNone(self.service)
        # conftest.py sets INSTANCE_BASE to https://test.example.com
        self.assertEqual(self.service.instance_url, "https://test.example.com")
        self.assertIsInstance(self.service._client_cache, dict)

    def test_get_client_creates_client(self):
        """Test that get_client creates a Mastodon client."""
        client = self.service.get_client("test_token")
        self.assertIsNotNone(client)

        # Verify it's cached
        client2 = self.service.get_client("test_token")
        self.assertIs(client, client2)

    def test_get_client_caching(self):
        """Test that clients are cached properly."""
        token1 = "token_abc"
        token2 = "token_xyz"

        client1 = self.service.get_client(token1)
        client2 = self.service.get_client(token2)
        client1_again = self.service.get_client(token1)

        # Different tokens should have different clients
        self.assertIsNot(client1, client2)

        # Same token should return cached client
        self.assertIs(client1, client1_again)

    def test_get_admin_client(self):
        """Test that get_admin_client uses admin token."""
        admin_client = self.service.get_admin_client()
        self.assertIsNotNone(admin_client)

    def test_get_bot_client(self):
        """Test that get_bot_client uses bot token."""
        bot_client = self.service.get_bot_client()
        self.assertIsNotNone(bot_client)

    @patch("app.services.mastodon_service.asyncio.to_thread")
    @patch("app.services.mastodon_service.Mastodon")
    async def test_exchange_oauth_code(self, mock_mastodon_class, mock_to_thread):
        """Test OAuth code exchange."""
        # Mock the log_in call
        mock_to_thread.return_value = "test_access_token"

        result = await self.service.exchange_oauth_code(
            code="auth_code", redirect_uri="https://example.com/callback"
        )

        self.assertEqual(result["access_token"], "test_access_token")
        self.assertEqual(result["token_type"], "Bearer")

    @patch("app.services.mastodon_service.asyncio.to_thread")
    async def test_verify_credentials(self, mock_to_thread):
        """Test credential verification."""
        # Mock the account_verify_credentials call
        mock_account = {
            "id": "123",
            "username": "testuser",
            "acct": "testuser@example.com",
            "display_name": "Test User",
        }
        mock_to_thread.return_value = mock_account

        result = await self.service.verify_credentials("test_token")

        self.assertEqual(result["id"], "123")
        self.assertEqual(result["username"], "testuser")

    @patch("app.services.mastodon_service.asyncio.to_thread")
    async def test_get_account(self, mock_to_thread):
        """Test fetching account information."""
        mock_account = {
            "id": "456",
            "username": "otheraccount",
            "acct": "otheraccount@example.com",
        }
        mock_to_thread.return_value = mock_account

        result = await self.service.get_account("456", use_admin=False)

        self.assertEqual(result["id"], "456")
        self.assertEqual(result["username"], "otheraccount")

    @patch("app.services.mastodon_service.asyncio.to_thread")
    async def test_get_account_statuses(self, mock_to_thread):
        """Test fetching account statuses."""
        mock_statuses = [
            {"id": "1", "content": "Status 1"},
            {"id": "2", "content": "Status 2"},
        ]
        mock_to_thread.return_value = mock_statuses

        result = await self.service.get_account_statuses("123", limit=20)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "1")

    @patch("app.services.mastodon_service.asyncio.to_thread")
    async def test_create_report(self, mock_to_thread):
        """Test creating a report."""
        mock_report = {"id": "report_123", "comment": "Test report"}
        mock_to_thread.return_value = mock_report

        result = await self.service.create_report(
            account_id="123", status_ids=["456"], comment="Test report", forward=False
        )

        self.assertEqual(result["id"], "report_123")

    def test_singleton_pattern(self):
        """Test that mastodon_service is a singleton."""
        from app.services.mastodon_service import mastodon_service

        self.assertIsNotNone(mastodon_service)
        # conftest.py sets INSTANCE_BASE to https://test.example.com
        self.assertEqual(mastodon_service.instance_url, "https://test.example.com")


if __name__ == "__main__":
    unittest.main()
