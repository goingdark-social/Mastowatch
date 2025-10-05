"""RQ Scheduler configuration for MastoWatch.

This module configures scheduled jobs using RQ Scheduler.
Replaces Celery Beat with a simpler, more observable scheduling system.
"""

import logging
from datetime import datetime
from rq import Queue
from rq_scheduler import Scheduler
from app.config import get_settings
from app.jobs.worker import get_redis_connection

logger = logging.getLogger(__name__)
settings = get_settings()


def get_scheduler():
    """Get RQ Scheduler instance."""
    redis_conn = get_redis_connection()
    return Scheduler(connection=redis_conn, queue_name='default')


def schedule_recurring_jobs(scheduler: Scheduler = None):
    """Schedule all recurring jobs.
    
    This function sets up the cron-like scheduled jobs that were previously
    managed by RQ Scheduler.
    """
    if scheduler is None:
        scheduler = get_scheduler()
    
    # Clear existing jobs to avoid duplicates
    for job in scheduler.get_jobs():
        scheduler.cancel(job)
    
    logger.info("Scheduling recurring jobs")
    
    # Import tasks here to avoid circular imports
    from app.jobs.tasks import (
        poll_admin_accounts,
        poll_admin_accounts_local,
        record_queue_stats,
    )
    
    # Schedule: poll_admin_accounts every 30 seconds (default)
    interval = settings.POLL_ADMIN_ACCOUNTS_INTERVAL
    scheduler.schedule(
        scheduled_time=datetime.utcnow(),
        func=poll_admin_accounts,
        interval=interval,
        repeat=None,  # Repeat indefinitely
        result_ttl=500,
        id='poll-admin-accounts',
    )
    logger.info(f"Scheduled poll_admin_accounts to run every {interval} seconds")
    
    # Schedule: poll_admin_accounts_local every 30 seconds (default)
    interval_local = settings.POLL_ADMIN_ACCOUNTS_LOCAL_INTERVAL
    scheduler.schedule(
        scheduled_time=datetime.utcnow(),
        func=poll_admin_accounts_local,
        interval=interval_local,
        repeat=None,
        result_ttl=500,
        id='poll-admin-accounts-local',
    )
    logger.info(f"Scheduled poll_admin_accounts_local to run every {interval_local} seconds")
    
    # Schedule: record_queue_stats every 60 seconds (default)
    stats_interval = settings.QUEUE_STATS_INTERVAL
    scheduler.schedule(
        scheduled_time=datetime.utcnow(),
        func=record_queue_stats,
        interval=stats_interval,
        repeat=None,
        result_ttl=500,
        id='queue-stats',
    )
    logger.info(f"Scheduled record_queue_stats to run every {stats_interval} seconds")
    
    logger.info("All recurring jobs scheduled successfully")


if __name__ == '__main__':
    # Run scheduler when executed directly
    scheduler = get_scheduler()
    schedule_recurring_jobs(scheduler)
    
    logger.info("Starting RQ Scheduler")
    scheduler.run()
