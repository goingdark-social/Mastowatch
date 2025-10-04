"""Service wrapper around mastodon.py library.

This is the ONLY interface for interacting with the Mastodon API.
All operations go through mastodon.py - no custom HTTP clients or OpenAPI clients.

This provides a centralized interface to the official Mastodon.py library,
handling client initialization, credential management, and providing async
wrappers for the synchronous mastodon.py API.
"""

import asyncio
import logging
from typing import Any

from app.config import get_settings
from mastodon import Mastodon, MastodonAPIError, MastodonNetworkError

logger = logging.getLogger(__name__)


class MastodonService:
    """Complete service wrapper for mastodon.py library.

    This is the SINGLE source for all Mastodon API operations.

    Provides:
    - Centralized client management with caching
    - Async wrappers for sync mastodon.py methods
    - Error handling and logging
    - Admin client access
    - Built-in rate limiting via mastodon.py
    - Type hints throughout
    """

    def __init__(self):
        self.settings = get_settings()
        self.instance_url = str(self.settings.INSTANCE_BASE).rstrip("/")
        self._client_cache: dict[str, Mastodon] = {}

    def get_client(self, access_token: str | None = None) -> Mastodon:
        """Get a configured Mastodon client instance.

        Args:
            access_token: Optional access token for authenticated requests.
                         If None, returns an unauthenticated client.

        Returns:
            Configured Mastodon client instance.
        """
        # Use token hash as cache key
        cache_key = access_token or "unauthenticated"

        if cache_key not in self._client_cache:
            client = Mastodon(
                access_token=access_token,
                api_base_url=self.instance_url,
                user_agent=self.settings.USER_AGENT,
                request_timeout=self.settings.HTTP_TIMEOUT,
                # mastodon.py has built-in rate limiting
                ratelimit_method="wait",
            )
            self._client_cache[cache_key] = client

        return self._client_cache[cache_key]

    def get_authenticated_client(self) -> Mastodon:
        """Get client with the configured Mastodon access token.

        Returns:
            Mastodon client configured with the access token.
        """
        return self.get_client(self.settings.MASTODON_ACCESS_TOKEN)


    async def exchange_oauth_code(
        self, code: str, redirect_uri: str, scopes: list[str] | None = None
    ) -> dict[str, Any]:
        """Exchange an OAuth authorization code for an access token.

        This is an async wrapper around mastodon.py's log_in method.

        Args:
            code: OAuth authorization code from the callback
            redirect_uri: Redirect URI used in the OAuth flow
            scopes: List of OAuth scopes (default: ['read', 'write', 'follow'])

        Returns:
            Dict containing access_token and other OAuth response data

        Raises:
            MastodonAPIError: If the API returns an error
            MastodonNetworkError: If there's a network issue
        """
        if scopes is None:
            scopes = ["read", "write", "follow"]

        # Create a client with OAuth credentials
        client = Mastodon(
            client_id=self.settings.MASTODON_CLIENT_KEY,
            client_secret=self.settings.MASTODON_CLIENT_SECRET,
            api_base_url=self.instance_url,
            user_agent=self.settings.USER_AGENT,
        )

        # log_in is synchronous, so wrap it in asyncio.to_thread
        try:
            access_token = await asyncio.to_thread(client.log_in, code=code, redirect_uri=redirect_uri, scopes=scopes)

            return {"access_token": access_token, "token_type": "Bearer"}

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"OAuth token exchange failed: {e}")
            raise

    async def verify_credentials(self, access_token: str) -> dict[str, Any]:
        """Verify credentials and get account information.

        Args:
            access_token: Access token to verify

        Returns:
            Account information dict

        Raises:
            MastodonAPIError: If credentials are invalid
        """
        client = self.get_client(access_token)

        try:
            # account_verify_credentials is synchronous
            account = await asyncio.to_thread(client.account_verify_credentials)
            return account

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Credential verification failed: {e}")
            raise

    async def get_account(self, account_id: str) -> dict[str, Any]:
        """Get account information.

        Args:
            account_id: Account ID to fetch

        Returns:
            Account information dict
        """
        client = self.get_authenticated_client()

        try:
            account = await asyncio.to_thread(client.account, account_id)
            return account

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch account {account_id}: {e}")
            raise

    async def get_account_statuses(
        self,
        account_id: str,
        limit: int = 20,
        max_id: str | None = None,
        exclude_reblogs: bool = False,
        exclude_replies: bool = False,
        only_media: bool = False,
    ) -> list[dict[str, Any]]:
        """Get statuses for an account.

        Args:
            account_id: Account ID
            limit: Maximum number of statuses to return
            max_id: Return statuses older than this ID
            exclude_reblogs: Exclude boosts
            exclude_replies: Exclude replies
            only_media: Only return statuses with media

        Returns:
            List of status dicts
        """
        client = self.get_authenticated_client()

        try:
            statuses = await asyncio.to_thread(
                client.account_statuses,
                account_id,
                limit=limit,
                max_id=max_id,
                exclude_reblogs=exclude_reblogs,
                exclude_replies=exclude_replies,
                only_media=only_media,
            )
            return statuses

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch statuses for account {account_id}: {e}")
            raise

    async def create_report(
        self,
        account_id: str,
        status_ids: list[str] | None = None,
        comment: str = "",
        forward: bool = False,
        category: str = "other",
        rule_ids: list[int] | None = None,
    ) -> dict[str, Any]:
        """Create a moderation report.

        Args:
            account_id: ID of account to report
            status_ids: IDs of statuses to include in report
            comment: Report comment
            forward: Whether to forward to remote instance
            category: Report category
            rule_ids: IDs of rules violated

        Returns:
            Report information dict
        """
        client = self.get_authenticated_client()

        try:
            report = await asyncio.to_thread(
                client.report,
                account_id=account_id,
                status_ids=status_ids or [],
                comment=comment,
                forward=forward,
                category=category,
                rule_ids=rule_ids or [],
            )
            return report

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to create report for account {account_id}: {e}")
            raise

    async def admin_suspend_account(self, account_id: str) -> dict[str, Any]:
        """Suspend an account (admin action).

        Args:
            account_id: Account ID to suspend

        Returns:
            Account information dict
        """
        client = self.get_authenticated_client()

        try:
            # Note: mastodon.py uses admin_account_moderate for actions
            account = await asyncio.to_thread(
                client.admin_account_moderate,
                account_id,
                action="suspend",
            )
            return account

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to suspend account {account_id}: {e}")
            raise

    async def admin_create_domain_block(
        self, domain: str, severity: str = "suspend", private_comment: str = ""
    ) -> dict[str, Any]:
        """Block a domain (admin action).

        Args:
            domain: Domain to block
            severity: Severity level ('silence', 'suspend', or 'noop')
            private_comment: Private comment about the block

        Returns:
            Domain block information dict
        """
        client = self.get_authenticated_client()

        try:
            domain_block = await asyncio.to_thread(
                client.admin_create_domain_block,
                domain=domain,
                severity=severity,
                private_comment=private_comment,
            )
            return domain_block

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to block domain {domain}: {e}")
            raise

    async def get_admin_accounts(
        self,
        origin: str | None = None,
        status: str | None = None,
        limit: int = 50,
        max_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Get admin account list.

        Args:
            origin: Filter by origin ('local' or 'remote')
            status: Filter by status
            limit: Maximum accounts to return
            max_id: Pagination cursor

        Returns:
            Tuple of (accounts list, next cursor)
        """
        client = self.get_authenticated_client()

        try:
            # Use admin_accounts_v2 which returns paginated results
            accounts = await asyncio.to_thread(
                client.admin_accounts_v2,
                origin=origin,
                status=status,
                max_id=max_id,
                limit=limit,
            )

            # mastodon.py handles pagination internally
            # Extract next cursor from the response if available
            next_cursor = None
            if hasattr(accounts, "_pagination_next") and accounts._pagination_next:
                # Try to extract max_id from pagination info
                next_params = accounts._pagination_next
                if "max_id" in next_params:
                    next_cursor = next_params["max_id"]

            return accounts, next_cursor

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch admin accounts: {e}")
            raise

    async def get_instance_info(self) -> dict[str, Any]:
        """Get instance information.

        Returns:
            Instance information dict
        """
        client = self.get_authenticated_client()

        try:
            instance = await asyncio.to_thread(client.instance)
            return instance

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch instance info: {e}")
            raise

    async def get_instance_rules(self) -> list[dict[str, Any]]:
        """Get instance rules.

        Returns:
            List of instance rules
        """
        client = self.get_authenticated_client()

        try:
            rules = await asyncio.to_thread(client.instance_rules)
            return rules if rules else []

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch instance rules: {e}")
            raise

    # Synchronous methods for backward compatibility
    # These are used in places that aren't async (like Celery tasks)

    def get_account_sync(self, account_id: str) -> dict[str, Any]:
        """Get account information (synchronous).

        Args:
            account_id: Account ID to fetch

        Returns:
            Account information dict
        """
        client = self.get_authenticated_client()

        try:
            account = client.account(account_id)
            return account

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch account {account_id}: {e}")
            raise

    def get_account_statuses_sync(
        self,
        account_id: str,
        limit: int = 20,
        max_id: str | None = None,
        exclude_reblogs: bool = False,
        exclude_replies: bool = False,
        only_media: bool = False,
    ) -> list[dict[str, Any]]:
        """Get statuses for an account (synchronous).

        Args:
            account_id: Account ID
            limit: Maximum number of statuses to return
            max_id: Return statuses older than this ID
            exclude_reblogs: Exclude boosts
            exclude_replies: Exclude replies
            only_media: Only return statuses with media

        Returns:
            List of status dicts
        """
        client = self.get_authenticated_client()

        try:
            statuses = client.account_statuses(
                account_id,
                limit=limit,
                max_id=max_id,
                exclude_reblogs=exclude_reblogs,
                exclude_replies=exclude_replies,
                only_media=only_media,
            )
            return statuses

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch statuses for account {account_id}: {e}")
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
        """Create a moderation report (synchronous).

        Args:
            account_id: ID of account to report
            status_ids: IDs of statuses to include in report
            comment: Report comment
            forward: Whether to forward to remote instance
            category: Report category
            rule_ids: IDs of rules violated

        Returns:
            Report information dict
        """
        client = self.get_authenticated_client()

        try:
            report = client.report(
                account_id=account_id,
                status_ids=status_ids or [],
                comment=comment,
                forward=forward,
                category=category,
                rule_ids=rule_ids or [],
            )
            return report

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to create report for account {account_id}: {e}")
            raise

    def get_admin_accounts_sync(
        self,
        origin: str | None = None,
        status: str | None = None,
        limit: int = 50,
        max_id: str | None = None,
    ) -> tuple[list[dict[str, Any]], str | None]:
        """Get admin account list (synchronous).

        Args:
            origin: Filter by origin ('local' or 'remote')
            status: Filter by status
            limit: Maximum accounts to return
            max_id: Pagination cursor

        Returns:
            Tuple of (accounts list, next cursor)
        """
        client = self.get_authenticated_client()

        try:
            # Use admin_accounts_v2 which returns paginated results
            accounts = client.admin_accounts_v2(
                origin=origin,
                status=status,
                max_id=max_id,
                limit=limit,
            )

            # mastodon.py handles pagination internally
            # Extract next cursor from the response if available
            next_cursor = None
            if hasattr(accounts, "_pagination_next") and accounts._pagination_next:
                # Try to extract max_id from pagination info
                next_params = accounts._pagination_next
                if "max_id" in next_params:
                    next_cursor = next_params["max_id"]

            return accounts, next_cursor

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch admin accounts: {e}")
            raise

    def get_instance_info_sync(self) -> dict[str, Any]:
        """Get instance information (synchronous).

        Returns:
            Instance information dict
        """
        client = self.get_authenticated_client()

        try:
            instance = client.instance()
            return instance

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch instance info: {e}")
            raise

    def get_instance_rules_sync(self) -> list[dict[str, Any]]:
        """Get instance rules (synchronous).

        Returns:
            List of instance rules
        """
        client = self.get_authenticated_client()

        try:
            rules = client.instance_rules()
            return rules if rules else []

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to fetch instance rules: {e}")
            raise

    def admin_account_action_sync(self, account_id: str, action_type: str, **kwargs) -> dict[str, Any]:
        """Perform an admin action on an account (synchronous).

        Args:
            account_id: Account ID to act on
            action_type: Type of action ('none', 'silence', 'suspend', etc.)
            **kwargs: Additional parameters (text, warning_preset_id, etc.)

        Returns:
            API response dict
        """
        client = self.get_authenticated_client()

        try:
            # mastodon.py provides admin_account_moderate method
            result = client.admin_account_moderate(account_id, action=action_type, **kwargs)
            return result

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to perform admin action {action_type} on account {account_id}: {e}")
            raise

    def admin_unsilence_account_sync(self, account_id: str) -> dict[str, Any]:
        """Unsilence an account (synchronous).

        Args:
            account_id: Account ID to unsilence

        Returns:
            API response dict
        """
        client = self.get_authenticated_client()

        try:
            result = client.admin_account_unsilence(account_id)
            return result

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to unsilence account {account_id}: {e}")
            raise

    def admin_unsuspend_account_sync(self, account_id: str) -> dict[str, Any]:
        """Unsuspend an account (synchronous).

        Args:
            account_id: Account ID to unsuspend

        Returns:
            API response dict
        """
        client = self.get_authenticated_client()

        try:
            result = client.admin_account_unsuspend(account_id)
            return result

        except (MastodonAPIError, MastodonNetworkError) as e:
            logger.error(f"Failed to unsuspend account {account_id}: {e}")
            raise


# Singleton instance
mastodon_service = MastodonService()
