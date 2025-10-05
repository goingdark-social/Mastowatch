"""RQ Worker configuration for MastoWatch.

This module configures RQ workers to process background jobs.
"""

import logging
from redis import Redis
from rq import Worker, Queue
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


def get_redis_connection():
    """Get Redis connection for RQ."""
    return Redis.from_url(settings.REDIS_URL)


def get_queue(name: str = 'default'):
    """Get an RQ queue by name."""
    redis_conn = get_redis_connection()
    return Queue(name, connection=redis_conn)


def create_worker(queue_names: list[str] = None):
    """Create an RQ worker for the specified queues.
    
    Args:
        queue_names: List of queue names to process. Defaults to ['default']
    
    Returns:
        Worker instance ready to process jobs
    """
    if queue_names is None:
        queue_names = ['default']
    
    redis_conn = get_redis_connection()
    queues = [Queue(name, connection=redis_conn) for name in queue_names]
    
    worker = Worker(queues, connection=redis_conn)
    logger.info(f"RQ worker created for queues: {queue_names}")
    
    return worker


if __name__ == '__main__':
    # Run worker when executed directly
    import sys
    
    queue_names = sys.argv[1:] if len(sys.argv) > 1 else ['default']
    worker = create_worker(queue_names)
    
    logger.info(f"Starting RQ worker for queues: {queue_names}")
    worker.work()
