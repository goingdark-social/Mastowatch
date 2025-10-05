import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# Set up environment for Mastodon v2 testing
os.environ.update(
    {
        "INSTANCE_BASE": "https://test.mastodon.social",
        "MASTODON_CLIENT_SECRET": "test_MASTODON_CLIENT_SECRET_123456789",
        "MASTODON_CLIENT_SECRET": "test_MASTODON_CLIENT_SECRET_123456789",
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

    @patch("app.services.mastodon_service.Mastodon.log_in", new_callable=MagicMock)
    async def test_exchange_oauth_code(self, mock_log_in):
        """Test OAuth code exchange using the official log_in method."""
        mock_log_in.return_value = "test_access_token"

        result = await self.service.exchange_oauth_code(code="auth_code", redirect_uri="https://example.com/callback")

        self.assertEqual(result["access_token"], "test_access_token")
        mock_log_in.assert_called_once()

    @patch("app.services.mastodon_service.Mastodon.account_verify_credentials", new_callable=MagicMock)
    async def test_verify_credentials(self, mock_verify):
        # Mock return value matching actual Mastodon Account object structure
        mock_verify.return_value = {
            "id": "123",
            "username": "testuser",
            "acct": "testuser@test.social",
            "display_name": "Test User",
            "locked": False,
            "bot": False,
            "created_at": "2023-01-01T00:00:00.000Z",
            "note": "<p>Test account</p>",
            "url": "https://test.mastodon.social/@testuser",
            "avatar": "https://test.mastodon.social/avatars/original/missing.png",
            "avatar_static": "https://test.mastodon.social/avatars/original/missing.png",
            "header": "https://test.mastodon.social/headers/original/missing.png",
            "header_static": "https://test.mastodon.social/headers/original/missing.png",
            "followers_count": 100,
            "following_count": 50,
            "statuses_count": 25,
            "last_status_at": "2023-01-01",
            "emojis": [],
            "fields": [],
        }

        result = await self.service.verify_credentials("test_token")
        self.assertEqual(result["username"], "testuser")
        self.assertEqual(result["id"], "123")

    @patch("app.services.mastodon_service.Mastodon.account", new_callable=MagicMock)
    async def test_get_account(self, mock_account):
        # Mock return value matching actual Mastodon Account object structure
        mock_account.return_value = {
            "id": "456",
            "username": "remoteuser",
            "acct": "remoteuser@remote.social",
            "display_name": "Remote User",
            "locked": False,
            "bot": False,
            "created_at": "2023-01-01T00:00:00.000Z",
            "note": "<p>Remote account</p>",
            "url": "https://remote.social/@remoteuser",
            "avatar": "https://remote.social/avatars/original/missing.png",
            "avatar_static": "https://remote.social/avatars/original/missing.png",
            "header": "https://remote.social/headers/original/missing.png",
            "header_static": "https://remote.social/headers/original/missing.png",
            "followers_count": 200,
            "following_count": 150,
            "statuses_count": 500,
            "last_status_at": "2023-01-02",
            "emojis": [],
            "fields": [],
        }
        result = await self.service.get_account("456")
        self.assertEqual(result["id"], "456")
        self.assertEqual(result["username"], "remoteuser")

    @patch("app.services.mastodon_service.Mastodon.account_statuses", new_callable=MagicMock)
    async def test_get_account_statuses(self, mock_statuses):
        # Mock return value matching actual Mastodon Status objects structure
        mock_statuses.return_value = [
            {
                "id": "1",
                "created_at": "2023-01-01T12:00:00.000Z",
                "in_reply_to_id": None,
                "in_reply_to_account_id": None,
                "sensitive": False,
                "spoiler_text": "",
                "visibility": "public",
                "language": "en",
                "uri": "https://test.mastodon.social/users/testuser/statuses/1",
                "url": "https://test.mastodon.social/@testuser/1",
                "replies_count": 0,
                "reblogs_count": 0,
                "favourites_count": 0,
                "content": "<p>Toot 1</p>",
                "reblog": None,
                "application": {"name": "Web", "website": None},
                "account": {
                    "id": "123",
                    "username": "testuser",
                    "acct": "testuser",
                    "display_name": "Test User",
                },
                "media_attachments": [],
                "mentions": [],
                "tags": [],
                "emojis": [],
                "card": None,
                "poll": None,
            },
            {
                "id": "2",
                "created_at": "2023-01-01T13:00:00.000Z",
                "in_reply_to_id": None,
                "in_reply_to_account_id": None,
                "sensitive": False,
                "spoiler_text": "",
                "visibility": "public",
                "language": "en",
                "uri": "https://test.mastodon.social/users/testuser/statuses/2",
                "url": "https://test.mastodon.social/@testuser/2",
                "replies_count": 0,
                "reblogs_count": 0,
                "favourites_count": 0,
                "content": "<p>Toot 2</p>",
                "reblog": None,
                "application": {"name": "Web", "website": None},
                "account": {
                    "id": "123",
                    "username": "testuser",
                    "acct": "testuser",
                    "display_name": "Test User",
                },
                "media_attachments": [],
                "mentions": [],
                "tags": [],
                "emojis": [],
                "card": None,
                "poll": None,
            },
        ]
        result = await self.service.get_account_statuses("123", limit=2)
        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["id"], "1")
        self.assertEqual(result[1]["id"], "2")

    @patch("app.services.mastodon_service.Mastodon.report", new_callable=MagicMock)
    async def test_create_report(self, mock_report):
        # Mock return value matching actual Mastodon Report object structure
        mock_report.return_value = {
            "id": "report_123",
            "action_taken": False,
            "action_taken_at": None,
            "category": "other",
            "comment": "Spam content",
            "forwarded": False,
            "created_at": "2023-01-01T12:00:00.000Z",
            "status_ids": ["1001"],
            "rule_ids": None,
            "target_account": {
                "id": "999",
                "username": "spammer",
                "acct": "spammer",
                "display_name": "Spammer Account",
            },
        }
        result = await self.service.create_report(
            account_id="999", status_ids=["1001"], comment="Spam content", forward=False
        )
        self.assertEqual(result["id"], "report_123")
        self.assertEqual(result["comment"], "Spam content")
        self.assertEqual(result["status_ids"], ["1001"])

    def test_singleton_pattern(self):
        from app.services.mastodon_service import mastodon_service

        self.assertIsNotNone(mastodon_service)
        self.assertEqual(mastodon_service.instance_url, "https://test.example.com")
