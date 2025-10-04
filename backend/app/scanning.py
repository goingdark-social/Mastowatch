import asyncio
import logging

from app.services.mastodon_service import mastodon_service
from mastodon import MastodonNetworkError

logger = logging.getLogger(__name__)


class ScanningSystem:
    ...

    async def get_next_accounts_to_scan(
        self, session_type: str, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[dict], str | None]:
        """Fetch next batch of accounts via v2 admin API."""
        try:
            # v2-only path: service handles admin_accounts_v2 and pagination
            accounts, next_cursor = await mastodon_service.get_admin_accounts(
                origin=session_type,
                status="active",
                limit=limit,
            )
            return accounts, next_cursor
        except MastodonNetworkError as e:
            logger.warning(f"Network timeout fetching {session_type} accounts, retrying: {e}")
            await asyncio.sleep(5)
            try:
                accounts, next_cursor = await mastodon_service.get_admin_accounts(
                    origin=session_type, status="active", limit=limit
                )
                return accounts, next_cursor
            except Exception as e2:
                logger.error(f"Retry failed fetching {session_type} accounts: {e2}")
                return [], None
        except Exception as e:
            logger.error(f"Fatal error fetching {session_type} accounts: {e}")
            return [], None

    async def scan_account_efficiently(self, account_data: dict, session_id: int) -> dict | None:
        """Async version using Mastodon v2 API only."""
        account_id = account_data.get("id")
        if not account_id or not self.should_scan_account(account_id, account_data):
            return None

        try:
            # Pull statuses directly from the v2 service layer
            statuses = await mastodon_service.get_account_statuses(
                account_id, limit=self.settings.MAX_STATUSES_TO_FETCH
            )
            media_statuses = await mastodon_service.get_account_statuses(
                account_id, limit=self.settings.MAX_STATUSES_TO_FETCH, only_media=True
            )

            seen = {s["id"] for s in statuses if "id" in s}
            statuses.extend([s for s in media_statuses if ("id" not in s) or (s["id"] not in seen)])

            # Continue with existing rule evaluation and DB writes...
            scan_result = self._evaluate_and_store_scan(account_id, account_data, statuses, session_id)
            return scan_result

        except MastodonNetworkError as e:
            logger.error(f"Network error scanning {account_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unhandled error scanning account {account_id}: {e}")
            return None
