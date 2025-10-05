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
    def exchange_oauth_code(self, code: str, redirect_uri: str) -> dict[str, Any]:
        """Exchange authorization code for token via /oauth/token.
        
        Uses the official log_in method from mastodon.py instead of private API.
        """
        client = Mastodon(
            client_id=self.settings.OAUTH_CLIENT_ID,
            client_secret=self.settings.OAUTH_CLIENT_SECRET,
            api_base_url=self.instance_url,
        )
        try:
            # Use the official log_in method with OAuth code flow
            # This returns the access token string, so we need to wrap it in a dict
            access_token = client.log_in(
                code=code,
                redirect_uri=redirect_uri,
                scopes=self.settings.OAUTH_SCOPE.split(),
            )
            return {"access_token": access_token}
        except (MastodonAPIError, MastodonNetworkError):
            logger.exception("OAuth code exchange failed")
            raise

    # ---------------------------------------------------
    # Account info
    # ---------------------------------------------------
    def verify_credentials(self, token: str) -> dict[str, Any]:
        client = self.get_client(token)
        try:
            return client.account_verify_credentials()
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Credential verification failed: {e}")
            raise

    def get_account(self, account_id: str) -> dict[str, Any]:
        client = self.get_admin_client()
        try:
            return client.account(account_id)
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch account {account_id}: {e}")
            raise

    def get_account_statuses(self, account_id: str, limit: int = 20) -> list[dict[str, Any]]:
        client = self.get_admin_client()
        try:
            return client.account_statuses(
                account_id,
                limit=limit,
            )
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch statuses for account {account_id}: {e}")
            raise

    # ---------------------------------------------------
    # Reports / moderation
    # ---------------------------------------------------
    def create_report(
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
            return client.report(
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

    def admin_suspend_account(self, account_id: str) -> dict[str, Any]:
        """Suspend an account using the admin moderation API.
        
        Uses admin_account_moderate which is the correct method name in mastodon.py.
        """
        client = self.get_admin_client()
        try:
            return client.admin_account_moderate(
                account_id,
                action="suspend",
            )
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to suspend account {account_id}: {e}")
            raise

    def admin_create_domain_block(
        self, domain: str, severity: str = "suspend", private_comment: str = ""
    ) -> dict[str, Any]:
        """Create a domain block using the admin API.
        
        Uses admin_create_domain_block which is the correct method name in mastodon.py.
        """
        client = self.get_admin_client()
        try:
            return client.admin_create_domain_block(
                domain=domain,
                severity=severity,
                private_comment=private_comment,
            )
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to block domain {domain}: {e}")
            raise

    def get_admin_accounts(self, origin=None, status=None, limit=50) -> tuple[list[dict[str, Any]], str | None]:
        """Fetch admin accounts list.
        
        Uses admin_accounts_v2 as recommended by mastodon.py docs.
        The non-versioned admin_accounts() is deprecated and may call v1 API.
        """
        client = self.get_admin_client()
        params = {"limit": limit}
        if origin:
            params["origin"] = origin
        if status:
            params["status"] = status
        try:
            result = client.admin_accounts_v2(**params)
            pagination_info = client.get_pagination_info(result, pagination_direction="next")
            next_cursor = pagination_info.get("max_id") if pagination_info else None
            return result, next_cursor
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch admin accounts: {e}")
            raise

    # ---------------------------------------------------
    # Instance info
    # ---------------------------------------------------
    def get_instance_info(self) -> dict[str, Any]:
        """Fetch instance information.
        
        Uses the non-versioned instance() method which automatically returns
        the latest version of instance info available on the server.
        """
        client = self.get_bot_client()
        try:
            return client.instance()
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch instance info: {e}")
            raise

    def get_instance_rules(self) -> list[dict[str, Any]]:
        """Fetch instance rules.
        
        Uses the non-versioned instance_rules() method.
        """
        client = self.get_bot_client()
        try:
            return client.instance_rules()
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch instance rules: {e}")
            raise

    # ---------------------------------------------------
    # Sync wrappers for enforcement service
    # ---------------------------------------------------
    def admin_account_action_sync(
        self, account_id: str, action_type: str, text: str | None = None, warning_preset_id: str | None = None
    ) -> dict[str, Any]:
        """Synchronous wrapper for admin account moderation.
        
        Used by enforcement_service which runs in Celery workers (sync context).
        """
        client = self.get_admin_client()
        try:
            return client.admin_account_moderate(
                account_id,
                action=action_type if action_type != "warn" else None,  # None action = warning only
                text=text,
                warning_preset_id=warning_preset_id,
            )
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to moderate account {account_id}: {e}")
            raise

    def admin_unsilence_account_sync(self, account_id: str) -> dict[str, Any]:
        """Synchronous wrapper for unsilencing accounts.
        
        Used by enforcement_service which runs in Celery workers (sync context).
        """
        client = self.get_admin_client()
        try:
            return client.admin_account_unsilence(account_id)
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to unsilence account {account_id}: {e}")
            raise

    def admin_unsuspend_account_sync(self, account_id: str) -> dict[str, Any]:
        """Synchronous wrapper for unsuspending accounts.
        
        Used by enforcement_service which runs in Celery workers (sync context).
        """
        client = self.get_admin_client()
        try:
            return client.admin_account_unsuspend(account_id)
        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to unsuspend account {account_id}: {e}")
            raise

    def create_report_sync(
        self,
        account_id: str,
        status_ids: list[str] | None = None,
        comment: str = "",
        forward: bool = False,
        category: str = "other",
        rule_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Synchronous wrapper for creating reports.
        
        Used by enforcement_service which runs in Celery workers (sync context).
        """
        client = self.get_admin_client()
        try:
            return client.report(
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


# Singleton
mastodon_service = MastodonService()
