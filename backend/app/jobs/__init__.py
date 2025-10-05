"""RQ job system for MastoWatch.

This module replaces Celery with RQ (Redis Queue) for simpler, synchronous job processing.
All jobs are plain Python functions - no decorators needed.
"""

# Re-export tasks for backward compatibility
from app.jobs.tasks import (
    analyze_and_maybe_report,
    check_domain_violations,
    poll_admin_accounts,
    poll_admin_accounts_local,
    process_expired_actions,
    process_new_report,
    process_new_status,
    record_queue_stats,
    scan_federated_content,
)

__all__ = [
    "analyze_and_maybe_report",
    "check_domain_violations",
    "poll_admin_accounts",
    "poll_admin_accounts_local",
    "process_expired_actions",
    "process_new_report",
    "process_new_status",
    "record_queue_stats",
    "scan_federated_content",
]
