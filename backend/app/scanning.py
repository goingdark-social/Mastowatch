import asyncio
import logging
from datetime import UTC, datetime
from typing import Any

from app.config import get_settings
from app.db import SessionLocal
from app.models import ScanSession
from app.services.mastodon_service import mastodon_service
from mastodon import MastodonNetworkError

logger = logging.getLogger(__name__)


class ScanningSystem:
    def __init__(self):
        """Initialize the scanning system."""
        self.settings = get_settings()

    # --- Session lifecycle -------------------------------------------------
    def start_scan_session(self, session_type: str, metadata: dict[str, Any] | None = None) -> str:
        """
        Create (or reuse) an active scan session and return its ID.
        jobs._poll_accounts(origin, ...) calls this with session_type="remote"/"local".
        """
        with SessionLocal() as db:
            # Reuse an active session of same type if one exists
            existing = (
                db.query(ScanSession)
                .filter(ScanSession.session_type == session_type, ScanSession.status == "active")
                .first()
            )
            if existing:
                return str(existing.id)

            sess = ScanSession(
                session_type=session_type,
                status="active",
                accounts_processed=0,
                total_accounts=0,
                current_cursor=None,
                started_at=datetime.now(UTC),
                rules_applied=(metadata or {}).get("rules_version"),
                session_metadata=metadata,
            )
            db.add(sess)
            db.commit()
            db.refresh(sess)
            return str(sess.id)

    def complete_scan_session(self, session_id: str | int, status: str = "completed") -> None:
        """Mark the session finished (used by jobs / tests)."""
        with SessionLocal() as db:
            sess = db.query(ScanSession).filter(ScanSession.id == session_id).first()
            if not sess:
                return
            sess.status = status
            sess.completed_at = datetime.now(UTC)
            db.commit()

    def should_scan_account(self, account_id: str, account_data: dict) -> bool:
        """Placeholder for account filtering logic."""
        # TODO: Implement actual filtering logic (rate limiting, caching, etc.)
        return True

    def _evaluate_and_store_scan(
        self, account_id: str, account_data: dict, statuses: list[dict], session_id: int
    ) -> dict | None:
        """Placeholder for rule evaluation and DB storage."""
        # TODO: Implement actual rule evaluation and storage
        return {"account_id": account_id, "violations_found": 0}

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
