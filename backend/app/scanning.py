import hashlib
import logging
from datetime import UTC, datetime, timedelta
from typing import Any, NamedTuple

from app.config import get_settings
from app.db import SessionLocal
from app.models import ContentScan, DomainAlert, ScanSession
from app.services.mastodon_service import mastodon_service
from app.services.rule_service import rule_service
from mastodon import MastodonNetworkError

logger = logging.getLogger(__name__)


class ScanProgress(NamedTuple):
    """Progress information for a scan session."""

    session_id: int
    session_type: str
    accounts_processed: int
    total_accounts: int


class ScanningSystem:
    def __init__(self):
        """Initialize the scanning system."""
        self.settings = get_settings()

    # --- Session lifecycle -------------------------------------------------
    def start_scan_session(self, session_type: str, metadata: dict[str, Any] | None = None) -> int:
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
                # Return numeric id for compatibility with callers/tests
                return existing.id

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
            # Return numeric id for compatibility with callers/tests
            return sess.id

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
        """Check if account should be scanned based on deduplication and caching logic."""
        # Check for recent scan with same content hash
        content_hash = self._calculate_content_hash(account_data)

        with SessionLocal() as db:
            recent_scan = (
                db.query(ContentScan)
                .filter(
                    ContentScan.mastodon_account_id == account_id,
                    ContentScan.content_hash == content_hash,
                    ContentScan.needs_rescan.is_(False),
                )
                .first()
            )

            if recent_scan:
                # Account content hasn't changed and doesn't need rescan
                return False

        return True

    def _calculate_content_hash(self, account_data: dict) -> str:
        """Calculate content hash for account deduplication."""
        # Extract key fields that indicate content changes
        content_parts = [
            account_data.get("username", ""),
            account_data.get("display_name", ""),
            account_data.get("note", ""),
            account_data.get("avatar", ""),
            account_data.get("header", ""),
            str(account_data.get("fields", [])),
        ]

        content_str = "|".join(content_parts)
        return hashlib.sha256(content_str.encode()).hexdigest()

    def _evaluate_and_store_scan(
        self, account_id: str, account_data: dict, statuses: list[dict], session_id: int
    ) -> dict | None:
        """Evaluate account against rules and store scan results."""
        # Get active rules
        rules, config, rules_version = rule_service.get_active_rules()

        if not rules:
            return {"account_id": account_id, "violations_found": 0}

        # Evaluate account
        violations = rule_service.evaluate_account(account_data, statuses)

        # Store scan result
        content_hash = self._calculate_content_hash(account_data)
        with SessionLocal() as db:
            # Upsert content scan
            existing_scan = (
                db.query(ContentScan)
                .filter(
                    ContentScan.mastodon_account_id == account_id,
                    ContentScan.content_hash == content_hash,
                )
                .first()
            )

            if existing_scan:
                existing_scan.last_scanned_at = datetime.now(UTC)
                existing_scan.scan_result = {"violations": len(violations)}
                existing_scan.rules_version = rules_version
            else:
                new_scan = ContentScan(
                    content_hash=content_hash,
                    mastodon_account_id=account_id,
                    scan_type="account",
                    scan_result={"violations": len(violations)},
                    rules_version=rules_version,
                )
                db.add(new_scan)

            db.commit()

        return {
            "account_id": account_id,
            "violations_found": len(violations),
            "score": sum(v.score for v in violations) if violations else 0,
            "hits": violations,
        }

    def get_next_accounts_to_scan(
        self, session_type: str, limit: int = 50, cursor: str | None = None
    ) -> tuple[list[dict], str | None]:
        """Fetch next batch of accounts via v2 admin API.

        This method calls the Mastodon service synchronously.
        """
        try:
            # Call service method directly - it's synchronous and always available
            accounts, next_cursor = mastodon_service.get_admin_accounts(
                origin=session_type, status="active", limit=limit
            )
            return accounts, next_cursor
        except MastodonNetworkError as e:
            logger.warning(f"Network timeout fetching {session_type} accounts, retrying: {e}")
            try:
                # brief sleep to mimic retry behaviour
                import time

                time.sleep(1)
                # Retry using service method
                accounts, next_cursor = mastodon_service.get_admin_accounts(
                    origin=session_type, status="active", limit=limit
                )
                return accounts, next_cursor
            except Exception as e2:
                logger.error(f"Retry failed fetching {session_type} accounts: {e2}")
                return [], None
        except Exception as e:
            logger.error(f"Fatal error fetching {session_type} accounts: {e}")
            return [], None

    def scan_account_efficiently(self, account_data: dict, session_id: int) -> dict | None:
        """Synchronous wrapper that scans an account using the Mastodon client.

        Calls sync client methods directly.

        IMPORTANT: account_data is an ADMIN ACCOUNT object from admin_accounts_v2(),
        which has structure: {"id": "admin_id", "account": {"id": "real_account_id", ...}}
        We need to use account_data["account"]["id"] for API calls, not account_data["id"]!
        """
        # Extract the nested account object from the admin account wrapper
        nested_account = account_data.get("account", {})
        account_id = nested_account.get("id")

        if not account_id or not self.should_scan_account(account_id, account_data):
            return None

        try:
            client = mastodon_service.get_admin_client()
            # Fetch statuses once (no need for separate media_only call)
            # Always use the standard account_statuses method from mastodon.py
            # CRITICAL: Use the real account ID, not the admin account ID!
            statuses = client.account_statuses(account_id, limit=self.settings.MAX_STATUSES_TO_FETCH)

            # Continue with existing rule evaluation and DB writes...
            scan_result = self._evaluate_and_store_scan(account_id, account_data, statuses, session_id)
            return scan_result

        except MastodonNetworkError as e:
            logger.error(f"Network error scanning {account_id}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unhandled error scanning account {account_id}: {e}")
            return None

    def _parse_next_cursor(self, link_header: str) -> str | None:
        """Parse next cursor from Link header for pagination."""
        if not link_header:
            return None

        # Look for rel="next" link
        import re

        next_match = re.search(r'<[^>]*max_id=([^>&]+)[^>]*>;\s*rel="next"', link_header)
        if next_match:
            return next_match.group(1)
        return None

    def _extract_domain(self, account_data: dict) -> str:
        """Extract domain from account data."""
        acct = account_data.get("acct", "")
        if "@" in acct:
            return acct.split("@")[-1]
        return "local"

    def _track_domain_violation(self, domain: str) -> None:
        """Track domain violation for defederation monitoring."""
        with SessionLocal() as db:
            # Upsert domain alert
            alert = db.query(DomainAlert).filter(DomainAlert.domain == domain).first()
            if alert:
                alert.violation_count += 1
                alert.last_violation_at = datetime.now(UTC)
            else:
                alert = DomainAlert(
                    domain=domain,
                    violation_count=1,
                    last_violation_at=datetime.now(UTC),
                )
                db.add(alert)
            db.commit()

    def _check_defederation_threshold(self, domain: str) -> None:
        """Check if domain should be automatically defederated."""
        with SessionLocal() as db:
            alert = db.query(DomainAlert).filter(DomainAlert.domain == domain).first()
            if alert and not alert.is_defederated and alert.violation_count >= alert.defederation_threshold:
                alert.is_defederated = True
                alert.defederated_at = datetime.now(UTC)
                alert.defederated_by = "automated_system"
                db.commit()

    def _scan_domain_content(self, domain: str, session_id: int) -> dict:
        """Scan content from a specific domain."""
        # Placeholder implementation - would need domain-specific scanning logic
        return {
            "accounts": [],
            "violations": [],
            "accounts_scanned": 0,
            "violations_found": 0,
            "session_id": session_id,
        }

    def _get_active_domains(self) -> list[str]:
        """Get list of active domains for federated scanning."""
        with SessionLocal() as db:
            # Get domains from recent accounts
            result = (
                db.query(ContentScan.mastodon_account_id)
                .filter(ContentScan.last_scanned_at > datetime.now(UTC) - timedelta(hours=24))
                .distinct()
                .limit(100)
                .all()
            )

            domains = set()
            for (account_id,) in result:
                # Extract domain from account_id (assuming format user@domain)
                if "@" in account_id:
                    domains.add(account_id.split("@")[-1])

            return list(domains)

    def scan_federated_content(self, target_domains: list[str] | None = None) -> dict:
        """Scan content across federated domains."""
        session_id = self.start_scan_session("federated")

        try:
            domains = target_domains or self._get_active_domains()
            total_scanned = 0
            total_violations = 0
            successful_scans = 0

            for domain in domains:
                try:
                    result = self._scan_domain_content(domain, session_id)
                    total_scanned += result.get("accounts_scanned", 0)
                    total_violations += result.get("violations_found", 0)
                    successful_scans += 1
                except Exception as e:
                    logger.error(f"Error scanning domain {domain}: {e}")

            return {
                "scanned_domains": len(domains),
                "accounts_scanned": total_scanned,
                "violations_found": total_violations,
                "session_id": session_id,
            }
        except Exception as e:
            logger.error(f"Error in federated scan: {e}")
            self.complete_scan_session(session_id, "failed")
            return {
                "scanned_domains": 0,
                "accounts_scanned": 0,
                "violations_found": 0,
                "error": str(e),
            }

    def invalidate_content_scans(self, rule_changes: bool = False) -> None:
        """Invalidate content scan cache."""
        with SessionLocal() as db:
            if rule_changes:
                # Mark all scans for rescan when rules change
                db.query(ContentScan).update({"needs_rescan": True})
            else:
                # Mark old scans for rescan (time-based invalidation)
                cutoff = datetime.now(UTC) - timedelta(hours=self.settings.CONTENT_CACHE_TTL)
                db.query(ContentScan).filter(ContentScan.last_scanned_at < cutoff).update({"needs_rescan": True})
            db.commit()

    def get_domain_alerts(self, limit: int = 100) -> list[dict]:
        """Get domain alerts for monitoring."""
        with SessionLocal() as db:
            alerts = db.query(DomainAlert).order_by(DomainAlert.violation_count.desc()).limit(limit).all()

            return [
                {
                    "domain": alert.domain,
                    "violation_count": alert.violation_count,
                    "last_violation_at": alert.last_violation_at.isoformat() if alert.last_violation_at else None,
                    "defederation_threshold": alert.defederation_threshold,
                    "is_defederated": alert.is_defederated,
                    "defederated_at": alert.defederated_at.isoformat() if alert.defederated_at else None,
                    "defederated_by": alert.defederated_by,
                    "notes": alert.notes,
                }
                for alert in alerts
            ]

    def get_scan_progress(self, session_id: int) -> ScanProgress | None:
        """Get progress information for a scan session."""
        with SessionLocal() as db:
            session = db.query(ScanSession).filter(ScanSession.id == session_id).first()
            if not session:
                return None

            return ScanProgress(
                session_id=session.id,
                session_type=session.session_type,
                accounts_processed=session.accounts_processed,
                total_accounts=session.total_accounts,
            )

    def _get_current_rules_snapshot(self) -> dict:
        """Get current rules snapshot for session tracking."""
        rules, config, rules_version = rule_service.get_active_rules()
        return {
            "rules_version": rules_version,
            "rule_count": len(rules),
            "report_threshold": config.get("report_threshold", 1.0),
        }
