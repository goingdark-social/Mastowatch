import os
import sys
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

# Set up environment for Mastodon v2 testing
os.environ.update(
    {
        "INSTANCE_BASE": "https://test.mastodon.social",
        "ADMIN_TOKEN": "test_admin_token_123456789",
        "BOT_TOKEN": "test_bot_token_123456789",
        "OAUTH_CLIENT_ID": "test_client_id",
        "OAUTH_CLIENT_SECRET": "test_client_secret",
    }
)

backend_path = Path(__file__).parent.parent / "backend"
sys.path.insert(0, str(backend_path))


class TestMastodonService(unittest.IsolatedAsyncioTestCase):
    """Updated tests for MastodonService with Mastodon API v2 support."""

    async def asyncSetUp(self):
        from app.services.mastodon_service import MastodonService

        self.service = MastodonService()

    async def test_service_initialization(self):
        self.assertIsNotNone(self.service)
        self.assertEqual(self.service.instance_url, "https://test.example.com")
        self.assertIsInstance(self.service._client_cache, dict)

    async def test_get_client_creates_and_caches_client(self):
        client = self.service.get_client("test_token")
        self.assertIsNotNone(client)
        same_client = self.service.get_client("test_token")
        self.assertIs(client, same_client)

    async def test_get_admin_and_bot_clients(self):
        admin = self.service.get_admin_client()
        bot = self.service.get_bot_client()
        self.assertIsNotNone(admin)
        self.assertIsNotNone(bot)

    @patch("app.services.mastodon_service.Mastodon.__api_request__", new_callable=AsyncMock)
    async def test_exchange_oauth_code(self, mock_api_request):
        mock_api_request.return_value = {
            "access_token": "test_access_token",
            "token_type": "Bearer",
            "scope": "read write follow",
            "created_at": 1234567890,
        }

        result = await self.service.exchange_oauth_code(code="auth_code", redirect_uri="https://example.com/callback")

        self.assertEqual(result["access_token"], "test_access_token")
        self.assertEqual(result["token_type"], "Bearer")

    @patch("app.services.mastodon_service.Mastodon.account_verify_credentials", new_callable=AsyncMock)
    async def test_verify_credentials(self, mock_verify):
        mock_verify.return_value = {"id": "123", "username": "testuser", "acct": "testuser@test.social"}

        result = await self.service.verify_credentials("test_token")
        self.assertEqual(result["username"], "testuser")

    @patch("app.services.mastodon_service.Mastodon.account", new_callable=AsyncMock)
    async def test_get_account(self, mock_account):
        mock_account.return_value = {"id": "456", "username": "remoteuser"}
        result = await self.service.get_account("456")
        self.assertEqual(result["id"], "456")

    @patch("app.services.mastodon_service.Mastodon.account_statuses", new_callable=AsyncMock)
    async def test_get_account_statuses(self, mock_statuses):
        mock_statuses.return_value = [{"id": "1", "content": "Toot 1"}, {"id": "2", "content": "Toot 2"}]
        result = await self.service.get_account_statuses("123", limit=2)
        self.assertEqual(len(result), 2)

    @patch("app.services.mastodon_service.Mastodon.report", new_callable=AsyncMock)
    async def test_create_report(self, mock_report):
        mock_report.return_value = {"id": "report_123", "comment": "Spam content"}
        result = await self.service.create_report(
            account_id="999", status_ids=["1001"], comment="Spam content", forward=False
        )
        self.assertEqual(result["id"], "report_123")

    def test_singleton_pattern(self):
        from app.services.mastodon_service import mastodon_service

        self.assertIsNotNone(mastodon_service)
        self.assertEqual(mastodon_service.instance_url, "https://test.example.com")
