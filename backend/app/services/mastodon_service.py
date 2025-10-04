import asyncio
import logging
from typing import Any

from app.config import get_settings
from mastodon import Mastodon, MastodonAPIError, MastodonNetworkError

logger = logging.getLogger(__name__)


class MastodonService:
    """Service wrapper around Mastodon.py (API v2-only)."""

    def __init__(self):
        self.settings = get_settings()
        self.instance_url = str(self.settings.INSTANCE_BASE).rstrip("/")
        self._client_cache: dict[str, Mastodon] = {}

    # ---------------------------------------------------
    # Client helpers
    # ---------------------------------------------------
    def get_client(self, token: str | None = None) -> Mastodon:
        key = token or "unauthenticated"
        if key not in self._client_cache:
            self._client_cache[key] = Mastodon(
                api_base_url=self.instance_url,
                access_token=token,
                user_agent=self.settings.USER_AGENT,
                ratelimit_method="wait",
                request_timeout=self.settings.HTTP_TIMEOUT,
            )
        return self._client_cache[key]

    def get_admin_client(self) -> Mastodon:
        """Get Mastodon client with admin privileges.

        Uses MASTODON_ACCESS_TOKEN which should have admin scope.
        """
        return self.get_client(self.settings.MASTODON_ACCESS_TOKEN)

    def get_bot_client(self) -> Mastodon:
        """Get Mastodon client for bot operations.

        Uses MASTODON_ACCESS_TOKEN. In the current setup, there's a single token
        with both admin and write permissions.
        """
        return self.get_client(self.settings.MASTODON_ACCESS_TOKEN)

    # ---------------------------------------------------
    # OAuth
    # ---------------------------------------------------
    async def exchange_oauth_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for token via /oauth/token."""
        client = Mastodon(
            client_id=self.settings.OAUTH_CLIENT_ID,
            client_secret=self.settings.OAUTH_CLIENT_SECRET,
            api_base_url=self.instance_url,
        )
        try:
            return await asyncio.to_thread(
                client._Mastodon__api_request,
                "POST",
                "/oauth/token",
                params={
                    "grant_type": "authorization_code",
                    "client_id": self.settings.OAUTH_CLIENT_ID,
                    "client_secret": self.settings.OAUTH_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "scope": self.settings.OAUTH_SCOPE,
                },
            )
        except (MastodonAPIError, MastodonNetworkError):
            logger.exception("OAuth code exchange failed")
            raise

    # ---------------------------------------------------
    # Account info
    # ---------------------------------------------------
    async def verify_credentials(self, token: str) -> dict[str, Any]:
        client = self.get_client(token)
        try:
            return await asyncio.to_thread(client.account_verify_credentials)
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Credential verification failed: {e}")
            raise

    async def get_account(self, account_id: str) -> dict[str, Any]:
        client = self.get_admin_client()
        try:
            return await asyncio.to_thread(client.account, account_id)
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch account {account_id}: {e}")
            raise

    async def get_account_statuses(self, account_id: str, limit: int = 20) -> list[dict[str, Any]]:
        client = self.get_admin_client()
        try:
            return await asyncio.to_thread(
                client.account_statuses,
                account_id,
                limit=limit,
            )
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch statuses for account {account_id}: {e}")
            raise

    # ---------------------------------------------------
    # Reports / moderation
    # ---------------------------------------------------
    async def create_report(
        self,
        account_id: str,
        status_ids: list[str] | None = None,
        comment: str = "",
        forward: bool = False,
        category: str = "other",
        rule_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        client = self.get_admin_client()
        try:
            return await asyncio.to_thread(
                client.report,
                account_id=account_id,
                status_ids=status_ids or [],
                comment=comment,
                forward=forward,
                category=category,
                rule_ids=rule_ids or [],
            )
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Report creation failed for account {account_id}: {e}")
            raise

    async def admin_suspend_account(self, account_id: str) -> dict[str, Any]:
        client = self.get_admin_client()
        try:
            return await asyncio.to_thread(
                client.admin_account_action_v2,
                account_id,
                action="suspend",
            )
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to suspend account {account_id}: {e}")
            raise

    async def admin_create_domain_block(
        self, domain: str, severity: str = "suspend", private_comment: str = ""
    ) -> dict[str, Any]:
        client = self.get_admin_client()
        try:
            return await asyncio.to_thread(
                client.admin_create_domain_block_v2,
                domain=domain,
                severity=severity,
                comment=private_comment,
            )
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to block domain {domain}: {e}")
            raise

    async def get_admin_accounts(self, origin=None, status=None, limit=50) -> list[dict[str, Any]]:
        client = self.get_admin_client()
        params = {"limit": limit}
        if origin:
            params["origin"] = origin
        if status:
            params["status"] = status
        try:
            result = await asyncio.to_thread(client.admin_accounts_v2, **params)
            pagination_info = await asyncio.to_thread(client.get_pagination_info, result, pagination_direction="next")
            next_cursor = pagination_info.get("max_id") if pagination_info else None
            return result, next_cursor
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch admin accounts: {e}")
            raise

    # ---------------------------------------------------
    # Instance info
    # ---------------------------------------------------
    async def get_instance_info(self) -> dict[str, Any]:
        client = self.get_bot_client()
        try:
            return await asyncio.to_thread(client.instance_v2)
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch instance info: {e}")
            raise

    async def get_instance_rules(self) -> list[dict[str, Any]]:
        client = self.get_bot_client()
        try:
            return await asyncio.to_thread(client.instance_rules_v2)
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch instance rules: {e}")
            raise


# Singleton
mastodon_service = MastodonService()
