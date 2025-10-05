"""Job management API for MastoWatch.

Provides REST endpoints to control and monitor RQ jobs.
"""

import logging
from typing import Any
from fastapi import APIRouter, HTTPException
from rq import Queue
from rq.job import Job
from rq.registry import StartedJobRegistry, FinishedJobRegistry, FailedJobRegistry
from app.jobs.worker import get_redis_connection, get_queue
from app.jobs.scheduler import get_scheduler, schedule_recurring_jobs
from app.oauth import require_admin_hybrid

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/queues", dependencies=[require_admin_hybrid])
def list_queues():
    """List all RQ queues and their status."""
    redis_conn = get_redis_connection()
    queue_names = Queue.all(connection=redis_conn)
    
    queues_info = []
    for queue in queue_names:
        q = Queue(queue.name, connection=redis_conn)
        queues_info.append({
            "name": q.name,
            "count": len(q),
            "started": StartedJobRegistry(queue=q).count,
            "finished": FinishedJobRegistry(queue=q).count,
            "failed": FailedJobRegistry(queue=q).count,
        })
    
    return {"queues": queues_info}


@router.get("/jobs", dependencies=[require_admin_hybrid])
def list_jobs(queue: str = "default", status: str = "queued"):
    """List jobs in a queue by status.
    
    Args:
        queue: Queue name (default: 'default')
        status: Job status - 'queued', 'started', 'finished', or 'failed'
    """
    redis_conn = get_redis_connection()
    q = Queue(queue, connection=redis_conn)
    
    if status == "queued":
        job_ids = q.job_ids
    elif status == "started":
        registry = StartedJobRegistry(queue=q)
        job_ids = registry.get_job_ids()
    elif status == "finished":
        registry = FinishedJobRegistry(queue=q)
        job_ids = registry.get_job_ids()
    elif status == "failed":
        registry = FailedJobRegistry(queue=q)
        job_ids = registry.get_job_ids()
    else:
        raise HTTPException(status_code=400, detail=f"Invalid status: {status}")
    
    jobs = []
    for job_id in job_ids:
        try:
            job = Job.fetch(job_id, connection=redis_conn)
            jobs.append({
                "id": job.id,
                "func_name": job.func_name,
                "created_at": job.created_at.isoformat() if job.created_at else None,
                "started_at": job.started_at.isoformat() if job.started_at else None,
                "ended_at": job.ended_at.isoformat() if job.ended_at else None,
                "status": job.get_status(),
                "result": str(job.result) if job.result else None,
                "exc_info": job.exc_info if hasattr(job, 'exc_info') else None,
            })
        except Exception as e:
            logger.warning(f"Failed to fetch job {job_id}: {e}")
            continue
    
    return {"queue": queue, "status": status, "jobs": jobs, "count": len(jobs)}


@router.get("/jobs/{job_id}", dependencies=[require_admin_hybrid])
def get_job(job_id: str):
    """Get details of a specific job."""
    redis_conn = get_redis_connection()
    
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        return {
            "id": job.id,
            "func_name": job.func_name,
            "args": job.args,
            "kwargs": job.kwargs,
            "created_at": job.created_at.isoformat() if job.created_at else None,
            "started_at": job.started_at.isoformat() if job.started_at else None,
            "ended_at": job.ended_at.isoformat() if job.ended_at else None,
            "status": job.get_status(),
            "result": str(job.result) if job.result else None,
            "exc_info": job.exc_info if hasattr(job, 'exc_info') else None,
            "meta": job.meta,
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Job not found: {e}")


@router.post("/jobs/{job_id}/cancel", dependencies=[require_admin_hybrid])
def cancel_job(job_id: str):
    """Cancel a queued or started job."""
    redis_conn = get_redis_connection()
    
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        job.cancel()
        return {"message": f"Job {job_id} cancelled", "id": job_id}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to cancel job: {e}")


@router.post("/jobs/{job_id}/requeue", dependencies=[require_admin_hybrid])
def requeue_job(job_id: str):
    """Requeue a failed job."""
    redis_conn = get_redis_connection()
    
    try:
        job = Job.fetch(job_id, connection=redis_conn)
        job.requeue()
        return {"message": f"Job {job_id} requeued", "id": job_id}
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Failed to requeue job: {e}")


@router.get("/scheduled", dependencies=[require_admin_hybrid])
def list_scheduled_jobs():
    """List all scheduled jobs."""
    scheduler = get_scheduler()
    
    jobs = []
    for job in scheduler.get_jobs():
        jobs.append({
            "id": job.id,
            "func_name": job.func_name,
            "scheduled_time": job.origin if hasattr(job, 'origin') else None,
            "interval": job.meta.get('interval') if hasattr(job, 'meta') else None,
            "repeat": job.meta.get('repeat') if hasattr(job, 'meta') else None,
        })
    
    return {"scheduled_jobs": jobs, "count": len(jobs)}


@router.post("/scheduled/reschedule", dependencies=[require_admin_hybrid])
def reschedule_jobs():
    """Reschedule all recurring jobs (useful after config changes)."""
    try:
        scheduler = get_scheduler()
        schedule_recurring_jobs(scheduler)
        return {"message": "Jobs rescheduled successfully"}
    except Exception as e:
        logger.error(f"Failed to reschedule jobs: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to reschedule jobs: {e}")


@router.post("/trigger/{task_name}", dependencies=[require_admin_hybrid])
def trigger_job(task_name: str):
    """Manually trigger a job.
    
    Args:
        task_name: Name of the task to trigger (e.g., 'poll_admin_accounts')
    """
    # Import tasks dynamically
    from app.jobs import tasks
    
    # Get the task function
    if not hasattr(tasks, task_name):
        raise HTTPException(status_code=404, detail=f"Task not found: {task_name}")
    
    task_func = getattr(tasks, task_name)
    
    # Enqueue the job
    queue = get_queue()
    job = queue.enqueue(task_func)
    
    return {
        "message": f"Job {task_name} triggered",
        "job_id": job.id,
        "task_name": task_name,
    }
