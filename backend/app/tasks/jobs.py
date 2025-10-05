from __future__ import annotations

import logging
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import redis
from app.config import get_settings
from app.db import SessionLocal
from app.metrics import (
    accounts_scanned,
    analyses_flagged,
    analysis_latency,
    cursor_lag_pages,
    queue_backlog,
    report_latency,
    reports_submitted,
)
from app.models import Analysis, ScheduledAction
from app.scanning import ScanningSystem
from app.services.enforcement_service import EnforcementService
from app.services.mastodon_service import mastodon_service
from app.services.rule_service import rule_service
from app.util import make_dedupe_key
from celery import shared_task
from sqlalchemy import insert, text
from sqlalchemy.sql import func

settings = get_settings()

# Visibility types that we analyze (public and unlisted content)
ANALYZABLE_VISIBILITY_TYPES = {"public", "unlisted"}

CURSOR_NAME = "admin_accounts"
CURSOR_NAME_LOCAL = "admin_accounts_local"

MAX_HISTORY_STATUSES = 20


def _get_client():
    """Get the bot Mastodon client from mastodon_service.

    Uses MASTODON_ACCESS_TOKEN for general authenticated operations.
    Tests patch this symbol in `app.tasks.jobs`, so keep a thin wrapper.
    """
    return mastodon_service.get_bot_client()


def _should_pause():
    # Honor PANIC_STOP from DB or env
    if settings.PANIC_STOP:
        return True
    try:
        with SessionLocal() as db:
            row = db.execute(text("SELECT value FROM config WHERE key='panic_stop'")).scalar()
            if isinstance(row, dict):
                return bool(row.get("enabled", False))
    except Exception:
        # In test environment or if config table doesn't exist, default to False
        pass
    return False


def _persist_account(a: dict):
    acct_obj = a.get("account") or {}
    if not acct_obj:
        return
    acct = acct_obj.get("acct") or ""
    domain = acct.split("@")[-1] if "@" in acct else "local"
    with SessionLocal() as db:
        # Database-agnostic account upsert
        account_id = acct_obj.get("id")
        existing = db.execute(
            text("SELECT id FROM accounts WHERE mastodon_account_id=:aid"), {"aid": account_id}
        ).first()

        if existing:
            db.execute(
                text(
                    "UPDATE accounts SET acct=:acct, domain=:domain, last_checked_at=CURRENT_TIMESTAMP WHERE mastodon_account_id=:aid"
                ),
                {"acct": acct, "domain": domain, "aid": account_id},
            )
        else:
            db.execute(
                text(
                    "INSERT INTO accounts (mastodon_account_id, acct, domain, last_checked_at) VALUES (:aid, :acct, :domain, CURRENT_TIMESTAMP)"
                ),
                {"aid": account_id, "acct": acct, "domain": domain},
            )
        db.commit()


def _poll_accounts(origin: str, cursor_name: str):
    if _should_pause():
        logging.warning(f"PANIC_STOP enabled; skipping {origin} account poll")
        return

    scanner = ScanningSystem()
    session_id = scanner.start_scan_session(origin)

    try:
        with SessionLocal() as db:
            pos = db.execute(text("SELECT position FROM cursors WHERE name=:n"), {"n": cursor_name}).scalar()

        pages = 0
        next_max = pos
        accounts_processed = 0

        while pages < settings.MAX_PAGES_PER_POLL:
            accounts, new_next = scanner.get_next_accounts_to_scan(origin, limit=settings.BATCH_SIZE, cursor=next_max)

            next_max = new_next

            if not accounts:
                break

            # On first page, estimate total accounts for progress tracking
            if pages == 0 and accounts:
                with SessionLocal() as db:
                    db.execute(
                        text("UPDATE scan_sessions SET total_accounts = :total WHERE id = :sid"),
                        {"total": len(accounts) * settings.MAX_PAGES_PER_POLL, "sid": session_id},
                    )
                    db.commit()

            for account_data in accounts:
                try:
                    _persist_account(account_data)

                    # Pass full admin object to scanner (includes admin fields + nested account)
                    scan_result = scanner.scan_account_efficiently(account_data, session_id)

                    if scan_result:
                        accounts_processed += 1
                        if scan_result.get("score", 0) > 0:
                            analyze_and_maybe_report.delay(
                                {
                                    "account": account_data.get("account"),
                                    "admin_obj": account_data,
                                    "scan_result": scan_result,
                                }
                            )

                except Exception as e:
                    logging.error(f"Error processing account: {e}")

            with SessionLocal() as db:
                # Database-agnostic cursor update
                cursor = db.execute(text("SELECT * FROM cursors WHERE name=:n"), {"n": cursor_name}).first()
                if cursor:
                    db.execute(
                        text("UPDATE cursors SET position=:pos, updated_at=CURRENT_TIMESTAMP WHERE name=:n"),
                        {"pos": new_next, "n": cursor_name},
                    )
                else:
                    db.execute(
                        text("INSERT INTO cursors (name, position, updated_at) VALUES (:n, :pos, CURRENT_TIMESTAMP)"),
                        {"n": cursor_name, "pos": new_next},
                    )

                # Update scan session cursor position for progress tracking
                db.execute(
                    text("UPDATE scan_sessions SET current_cursor = :cursor WHERE id = :sid"),
                    {"cursor": new_next, "sid": session_id},
                )
                db.commit()

            cursor_lag_pages.labels(cursor=cursor_name).set(1.0 if new_next else 0.0)

            if not new_next:
                break

            pages += 1

        scanner.complete_scan_session(session_id)
        logging.info(
            f"{origin.capitalize()} account poll completed: {accounts_processed} accounts processed, {pages} pages"
        )

    except Exception as e:
        logging.error(f"Error in {origin} account poll: {e}")
        scanner.complete_scan_session(session_id, "failed")


@shared_task(
    name="app.tasks.jobs.poll_admin_accounts",
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
)
def poll_admin_accounts():
    """Poll remote admin accounts"""
    _poll_accounts("remote", CURSOR_NAME)


@shared_task(
    name="app.tasks.jobs.poll_admin_accounts_local",
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
)
def poll_admin_accounts_local():
    """Poll local admin accounts"""
    _poll_accounts("local", CURSOR_NAME_LOCAL)


@shared_task(name="app.tasks.jobs.record_queue_stats")
def record_queue_stats():
    try:
        q = "celery"
        r = redis.from_url(settings.REDIS_URL, decode_responses=False)
        # Celery default redis backend uses 'celery' list for queue
        backlog = r.llen(q)
        queue_backlog.labels(queue=q).set(float(backlog))
    except Exception as e:
        logging.warning("record_queue_stats: %s", e)


@shared_task(
    name="app.tasks.jobs.scan_federated_content",
    autoretry_for=(Exception,),
    retry_backoff=5,
    retry_backoff_max=300,
    retry_jitter=True,
)
def scan_federated_content(target_domains=None):
    """Scan content across federated domains for violations"""
    if _should_pause():
        logging.warning("PANIC_STOP enabled; skipping federated content scan")
        return

    scanner = ScanningSystem()

    try:
        results = scanner.scan_federated_content(target_domains)
        logging.info(f"Federated scan completed: {results}")
        return results
    except Exception as e:
        logging.error(f"Error in federated content scan: {e}")
        raise


@shared_task(
    name="app.tasks.jobs.check_domain_violations",
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
)
def check_domain_violations():
    """Check and update domain violation tracking"""
    if _should_pause():
        logging.warning("PANIC_STOP enabled; skipping domain violation check")
        return

    scanner = ScanningSystem()

    try:
        domain_alerts = scanner.get_domain_alerts(100)
        defederated_count = sum(1 for alert in domain_alerts if alert["is_defederated"])

        logging.info(
            f"Domain violation check completed: {len(domain_alerts)} domains tracked, {defederated_count} defederated"
        )
        return {
            "domains_tracked": len(domain_alerts),
            "defederated_domains": defederated_count,
            "high_risk_domains": sum(
                1 for alert in domain_alerts if alert["violation_count"] >= alert["defederation_threshold"] * 0.8
            ),
        }
    except Exception as e:
        logging.error(f"Error checking domain violations: {e}")
        raise


@shared_task(
    name="app.tasks.jobs.analyze_and_maybe_report",
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
)
def analyze_and_maybe_report(payload: dict):
    try:
        if _should_pause():
            logging.warning("PANIC_STOP enabled; skipping analyze/report")
            return

        started = time.time()

        # Allow both raw admin object or normalized dict
        acct = payload.get("account") or payload.get("admin_obj", {}).get("account") or {}
        acct_id = acct.get("id")
        if not acct_id:
            return

        client: Any = _get_client()
        enforcement_service: EnforcementService = EnforcementService()

        cached_result = payload.get("scan_result")
        violated_rule_names: set[str] = set()
        if cached_result:
            score = cached_result.get("score", 0)
            hits = [(h["rule"], h["weight"], h["evidence"]) for h in cached_result.get("rule_hits", [])]
            for rk, _, _ in hits:
                name = rk.split("/", 1)[1] if "/" in rk else rk
                violated_rule_names.add(name)
        else:
            # Tests sometimes include recent statuses in the payload to avoid network calls
            statuses: list[dict[str, Any]] | None = payload.get("statuses") or payload.get("recent_statuses")
            if statuses is None:
                # Use Mastodon.py client to fetch statuses
                try:
                    statuses = client.account_statuses(acct_id, limit=settings.MAX_STATUSES_TO_FETCH)
                except Exception as e:
                    logging.warning(f"Could not fetch statuses for account {acct_id}: {e}")
                    statuses = []

            violations: list[Any] = rule_service.evaluate_account(acct, statuses or [])
            score = sum(v.score for v in violations)
            hits = [(f"{v.rule_type}/{v.rule_name}", v.score, v.evidence or {}) for v in violations]
            violated_rule_names = {v.rule_name for v in violations}

        rule_evidence_map: dict[str, dict[str, Any]] = {}
        for rk, _, ev in hits:
            name = rk.split("/", 1)[1] if "/" in rk else rk
            if name not in rule_evidence_map:
                rule_evidence_map[name] = ev

        accounts_scanned.inc()
        analysis_latency.observe(max(0.0, time.time() - started))

        if not hits:
            return

        with SessionLocal() as db:
            for rk, w, ev in hits:
                db.execute(
                    insert(Analysis).values(
                        mastodon_account_id=acct_id,
                        status_id=ev.get("status_id"),
                        rule_key=rk,
                        score=w,
                        evidence=ev,
                    )
                )
                analyses_flagged.labels(rule=rk).inc()
            db.commit()

        rules, config, ruleset_sha = rule_service.get_active_rules()
        rule_map = {r.name: r for r in rules}

        def schedule(action: str, duration: int) -> None:
            expires = datetime.now(UTC) + timedelta(seconds=duration)
            with SessionLocal() as db:
                existing = (
                    db.query(ScheduledAction)
                    .filter_by(mastodon_account_id=acct_id, action_to_reverse=action)
                    .one_or_none()
                )
                if existing:
                    if expires > existing.expires_at:
                        existing.expires_at = expires
                else:
                    db.add(
                        ScheduledAction(
                            mastodon_account_id=acct_id,
                            action_to_reverse=action,
                            expires_at=expires,
                        )
                    )
                db.commit()

        performed: set[str] = set()
        for name in violated_rule_names:
            rule = rule_map.get(name)
            if not rule:
                continue
            evidence = rule_evidence_map.get(name)
            action = rule.action_type
            if action == "warn" and "warn" not in performed:
                enforcement_service.warn_account(
                    acct_id,
                    text=rule.action_warning_text,
                    warning_preset_id=rule.warning_preset_id,
                    rule_id=rule.id,
                    evidence=evidence,
                )
                performed.add("warn")
            elif action == "silence":
                if "silence" not in performed:
                    enforcement_service.silence_account(
                        acct_id,
                        text=rule.action_warning_text,
                        warning_preset_id=rule.warning_preset_id,
                        rule_id=rule.id,
                        evidence=evidence,
                    )
                    performed.add("silence")
                if not settings.DRY_RUN and rule.action_duration_seconds:
                    schedule("silence", rule.action_duration_seconds)
            elif action == "suspend":
                if "suspend" not in performed:
                    enforcement_service.suspend_account(
                        acct_id,
                        text=rule.action_warning_text,
                        warning_preset_id=rule.warning_preset_id,
                        rule_id=rule.id,
                        evidence=evidence,
                    )
                    performed.add("suspend")
                if not settings.DRY_RUN and rule.action_duration_seconds:
                    schedule("suspend", rule.action_duration_seconds)

        if float(score) < float(config.get("report_threshold", 1.0)):
            return

        # Track domain violation
        domain = acct.get("acct", "").split("@")[-1] if "@" in acct.get("acct", "") else "local"
        if domain != "local":
            scanner = ScanningSystem()
            scanner.track_domain_violation(domain)

        # Prepare report
        status_ids = [h[2].get("status_id") for h in hits if h[2].get("status_id")]
        comment = f"[AUTO] score={score:.2f}; hits=" + ", ".join(h[0] for h in hits)
        dedupe = make_dedupe_key(
            acct_id,
            status_ids,
            settings.POLICY_VERSION,
            ruleset_sha,
            {"hit_count": len(hits)},
        )

        with SessionLocal() as db:
            # Database-agnostic report insert with deduplication
            existing = db.execute(text("SELECT id FROM reports WHERE dedupe_key=:dk"), {"dk": dedupe}).first()

            if existing:
                inserted_id = None  # Already exists, do nothing
            else:
                # Insert and get the ID - SQLite compatible approach
                db.execute(
                    text(
                        "INSERT INTO reports (mastodon_account_id, status_id, mastodon_report_id, dedupe_key, comment, created_at) VALUES (:aid, :sid, :rid, :dk, :comment, CURRENT_TIMESTAMP)"
                    ),
                    {
                        "aid": acct_id,
                        "sid": status_ids[0] if status_ids else None,
                        "rid": None,
                        "dk": dedupe,
                        "comment": comment,
                    },
                )
                # Get the ID of the inserted record
                inserted_id = db.execute(text("SELECT id FROM reports WHERE dedupe_key=:dk"), {"dk": dedupe}).scalar()
            db.commit()
            if inserted_id is None:
                return

        if settings.DRY_RUN:
            logging.info(
                "DRY-RUN report acct=%s score=%.2f hits=%d",
                acct.get("acct"),
                score,
                len(hits),
            )
            return

        category = settings.REPORT_CATEGORY_DEFAULT
        forward = settings.FORWARD_REMOTE_REPORTS if "@" in acct.get("acct", "") else False

        report_client: Any = _get_client()
        # Use mastodon.py's report method
        result = report_client.report(
            account_id=acct_id,
            comment=comment,
            status_ids=status_ids,
            category=category,
            forward=forward,
            rule_ids=None,
        )
        rep_id = result["id"]

        with SessionLocal() as db:
            db.execute(
                text("UPDATE reports SET mastodon_report_id = :rid WHERE dedupe_key = :dk"),
                {"rid": rep_id, "dk": dedupe},
            )
            db.commit()

        reports_submitted.labels(domain=domain).inc()
        report_latency.observe(max(0.0, time.time() - started))

        return result

    except Exception as e:
        logging.exception("analyze_and_maybe_report error: %s", e)
        raise


@shared_task(
    name="app.tasks.jobs.process_expired_actions",
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_expired_actions():
    """Processes scheduled actions that have expired and reverses them."""
    logging.info("Running process_expired_actions task...")

    _get_client()
    enforcement_service = EnforcementService()

    with SessionLocal() as session:
        now = func.now()
        expired_actions = session.query(ScheduledAction).filter(ScheduledAction.expires_at <= now).all()

        for action in expired_actions:
            try:
                logging.info(f"Reversing action {action.action_to_reverse} for account {action.mastodon_account_id}")
                if action.action_to_reverse == "silence":
                    enforcement_service.unsilence_account(action.mastodon_account_id)
                elif action.action_to_reverse == "suspend":
                    enforcement_service.unsuspend_account(action.mastodon_account_id)
                # Add other reversal actions as needed

                session.delete(action)
                session.commit()
                logging.info(
                    f"Successfully reversed and deleted scheduled action for account {action.mastodon_account_id}"
                )
            except Exception as e:
                logging.error(f"Error reversing action for account {action.mastodon_account_id}: {e}")
                session.rollback()  # Rollback in case of error to keep the action in the queue


@shared_task(
    name="app.tasks.jobs.process_new_report",
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_new_report(report_payload: dict):
    """Processes a new report webhook payload.

    Mastodon API v2: receives the report object directly (not wrapped).
    The webhook handler extracts payload["object"] and passes it here.
    """
    logging.info(f"Processing new report: {report_payload.get('id')}")
    try:
        if _should_pause():
            logging.warning("PANIC_STOP enabled; skipping new report processing")
            return

        # v2: report_payload is already the report object
        report_data = report_payload
        account_data = report_data.get("target_account", {})  # Should analyze the target account, not the reporter
        status_ids = report_data.get("status_ids", [])

        if not account_data.get("id"):
            logging.warning("Report payload missing account ID, skipping processing.")
            return

        client = _get_client()
        enforcement_service = EnforcementService()

        # Fetch full account details if needed (webhook payload might be partial)
        # For now, assume webhook payload has enough info for initial scan
        # In a real scenario, you might call client.account(account_data['id'])

        # Fetch statuses related to the report
        statuses = []
        for _s_id in status_ids:
            try:
                # This is a simplified approach. Tests mock client.get_account_statuses
                if hasattr(client, "get_account_statuses"):
                    account_statuses = client.get_account_statuses(
                        account_id=account_data["id"], limit=settings.MAX_STATUSES_TO_FETCH
                    )
                else:
                    account_statuses = client.account_statuses(account_data["id"], limit=settings.MAX_STATUSES_TO_FETCH)
                statuses = [s for s in account_statuses if s.get("id") in status_ids]
                break  # Assuming we only need to fetch once
            except Exception as e:
                logging.warning(f"Could not fetch statuses for report {report_data.get('id')}: {e}")

        # Evaluate account and statuses against rules
        violations = rule_service.evaluate_account(account_data, statuses)

        if violations:
            logging.info(f"Report {report_data.get('id')} triggered {len(violations)} violations.")
            for violation in violations:
                logging.info(
                    f"  Violation: {violation.rule_name}, Score: {violation.score}, Action: {violation.action_type}"
                )

                # Decide on action based on the rule's action_type and trigger_threshold
                # For 'report' action, we need to ensure it's not already reported
                if violation.action_type == "report":
                    # Check if a report for this account/status combination already exists
                    # This is a simplified check, a more robust one might involve dedupe_key
                    if not report_data.get(
                        "mastodon_report_id"
                    ):  # Assuming this field indicates if it's already reported
                        logging.info(
                            f"Attempting to perform automated report for account {account_data['id']} due to rule {violation.rule_name}"
                        )
                        enforcement_service.perform_account_action(
                            account_id=account_data["id"],
                            action_type=violation.action_type,
                            report_id=report_data.get("id"),  # Pass the original report ID if available
                            comment=f"Automated report: {violation.rule_name} (Score: {violation.score})",
                            status_ids=[s.get("id") for s in statuses if s.get("id")],  # Pass relevant status IDs
                        )
                elif violation.action_type in [
                    "silence",
                    "suspend",
                    "disable",
                    "sensitive",
                    "domain_block",
                ]:
                    logging.info(
                        f"Attempting to perform automated action {violation.action_type} for account {account_data['id']} due to rule {violation.rule_name}"
                    )
                    enforcement_service.perform_account_action(
                        account_id=account_data["id"],
                        action_type=violation.action_type,
                        comment=f"Automated action: {violation.rule_name} (Score: {violation.score})",
                        duration=violation.action_duration_seconds,  # Pass duration if applicable
                        warning_text=violation.action_warning_text,  # Pass warning text if applicable
                        warning_preset_id=violation.warning_preset_id,  # Pass warning preset if applicable
                    )
        else:
            logging.info(f"Report {report_data.get('id')} did not trigger any violations.")

    except Exception as e:
        logging.exception(f"Error processing new report: {e}")
        raise


@shared_task(
    name="app.tasks.jobs.process_new_status",
    autoretry_for=(Exception,),
    retry_backoff=2,
    retry_backoff_max=60,
    retry_jitter=True,
)
def process_new_status(status_payload: dict):
    """Processes a new status webhook payload for high-speed analysis.

    Mastodon API v2: receives the status object directly (not wrapped).
    The webhook handler extracts payload["object"] and passes it here.
    """
    logging.info(f"Processing new status: {status_payload.get('id')}")
    try:
        if _should_pause():
            logging.warning("PANIC_STOP enabled; skipping new status processing")
            return

        # v2: status_payload is already the status object
        status_data = status_payload
        account_data = status_data.get("account", {})
        if not account_data.get("id"):
            logging.warning("Status payload missing account ID, skipping processing.")
            return

        client = _get_client()
        try:
            # Mastodon.py client has account_statuses() method
            history = client.account_statuses(
                account_data["id"],
                limit=MAX_HISTORY_STATUSES,
                exclude_reblogs=True,
            )
        except Exception as e:
            logging.warning(f"Could not fetch account statuses: {e}")
            history = []
        history = [s for s in history if s.get("visibility") in ANALYZABLE_VISIBILITY_TYPES]
        combined = [status_data]
        seen = {status_data.get("id")}
        for s in history:
            s_id = s.get("id")
            if s_id and s_id not in seen:
                combined.append(s)
                seen.add(s_id)
        public_only = [s for s in combined if s.get("visibility") == "public"]

        enforcement_service = EnforcementService()
        violations = rule_service.evaluate_account(
            {**account_data, "recent_public_statuses": public_only},
            combined,
        )

        if violations:
            logging.info(f"Status {status_data.get('id')} triggered {len(violations)} violations.")
            for violation in violations:
                logging.info(
                    f"  Violation: {violation.rule_name}, Score: {violation.score}, Action: {violation.action_type}"
                )

                # Decide on action based on the rule's action_type and trigger_threshold
                if violation.action_type in [
                    "silence",
                    "suspend",
                    "disable",
                    "sensitive",
                    "domain_block",
                ]:
                    logging.info(
                        f"Attempting to perform automated action {violation.action_type} for account {account_data['id']} due to rule {violation.rule_name}"
                    )
                    enforcement_service.perform_account_action(
                        account_id=account_data["id"],
                        action_type=violation.action_type,
                        comment=f"Automated action: {violation.rule_name} (Score: {violation.score})",
                        duration=violation.action_duration_seconds,  # Pass duration if applicable
                        warning_text=violation.action_warning_text,  # Pass warning text if applicable
                        warning_preset_id=violation.warning_preset_id,  # Pass warning preset if applicable
                    )
                elif violation.action_type == "report":
                    # For status-triggered reports, create a new report
                    logging.info(
                        f"Attempting to create automated report for account {account_data['id']} due to rule {violation.rule_name}"
                    )
                    enforcement_service.perform_account_action(
                        account_id=account_data["id"],
                        action_type=violation.action_type,
                        comment=f"Automated report: {violation.rule_name} (Score: {violation.score})",
                        status_ids=[status_data.get("id")],  # Report the specific status
                    )
        else:
            logging.info(f"Status {status_data.get('id')} did not trigger any violations.")

    except Exception as e:
        logging.exception(f"Error processing new status: {e}")
        raise
