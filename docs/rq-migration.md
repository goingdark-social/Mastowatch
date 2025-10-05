# RQ Job System Migration Guide

This document describes the migration from Celery to RQ (Redis Queue) for background job processing in MastoWatch.

## Overview

MastoWatch has migrated from Celery to RQ for simpler, more observable, and maintainable background job processing. This change eliminates complexity while improving visibility and control over scheduled jobs.

## Why RQ?

### Problems with Celery

1. **Async/Sync Mismatch**: Celery's async features added complexity without benefit since mastodon.py is synchronous
2. **Opaque Scheduling**: Celery Beat ran in isolation with no API visibility into job status or history
3. **Configuration Complexity**: Required separate worker and beat processes with complex SQLAlchemy scheduler configuration
4. **Testing Overhead**: Dual async/sync patterns doubled testing burden

### Benefits of RQ

1. **Simplicity**: Jobs are plain Python functions - no decorators needed
2. **Visibility**: Built-in web dashboard and REST API for job monitoring
3. **Synchronous**: Matches the synchronous nature of mastodon.py
4. **Observable**: Full job lifecycle tracking with detailed status and history
5. **Easy Testing**: Simple to mock and test synchronous job calls

## Architecture

```
┌─────────────────────────────────────────────┐
│         FastAPI Application                  │
│  (Enqueues jobs via RQ)                     │
└──────────────┬──────────────────────────────┘
               │
               ▼
┌──────────────────────┐
│   Redis (Queue)      │
│  Job Storage         │
└──────────┬───────────┘
           │
           ▼
┌──────────────────────┐     ┌─────────────────┐
│   RQ Worker          │     │  RQ Scheduler   │
│  (Processes jobs)    │ ◄───┤  (Recurring)    │
└──────────────────────┘     └─────────────────┘
           │
           ▼
┌──────────────────────┐
│  RQ Dashboard        │
│  (Monitoring)        │
└──────────────────────┘
```

## Job System Components

### 1. Worker (`backend/app/jobs/worker.py`)

Processes jobs from Redis queues. Multiple workers can run in parallel.

```python
from app.jobs.worker import create_worker

# Create and run worker
worker = create_worker(['default'])
worker.work()
```

### 2. Scheduler (`backend/app/jobs/scheduler.py`)

Manages recurring jobs (cron-like scheduling). Replaces Celery Beat.

```python
from app.jobs.scheduler import get_scheduler, schedule_recurring_jobs

# Schedule recurring jobs
scheduler = get_scheduler()
schedule_recurring_jobs(scheduler)
scheduler.run()
```

### 3. Tasks (`backend/app/jobs/tasks.py`)

Plain Python functions - no decorators needed. Same functions as before, just without `@shared_task`.

```python
# RQ job - just a normal function
def poll_admin_accounts():
    """Poll admin accounts for violations."""
    # Implementation...
```

### 4. Job Management API (`backend/app/jobs/api.py`)

REST API for controlling and monitoring jobs.

Endpoints:
- `GET /jobs/queues` - List all queues and their status
- `GET /jobs/jobs?queue=default&status=queued` - List jobs
- `GET /jobs/jobs/{job_id}` - Get job details
- `POST /jobs/jobs/{job_id}/cancel` - Cancel a job
- `POST /jobs/jobs/{job_id}/requeue` - Requeue a failed job
- `GET /jobs/scheduled` - List scheduled jobs
- `POST /jobs/scheduled/reschedule` - Reschedule all recurring jobs
- `POST /jobs/trigger/{task_name}` - Manually trigger a job

## Scheduled Jobs

The following jobs run on a recurring schedule:

| Job | Interval | Description |
|-----|----------|-------------|
| `poll_admin_accounts` | 30s (default) | Scan remote accounts for violations |
| `poll_admin_accounts_local` | 30s (default) | Scan local accounts for violations |
| `record_queue_stats` | 60s (default) | Update queue metrics |

Intervals can be configured via environment variables:
- `POLL_ADMIN_ACCOUNTS_INTERVAL`
- `POLL_ADMIN_ACCOUNTS_LOCAL_INTERVAL`
- `QUEUE_STATS_INTERVAL`

## Enqueuing Jobs

### From API Endpoints

```python
from app.jobs.worker import get_queue
from app.jobs.tasks import process_new_status

@router.post("/process")
def process_status(status_data: dict):
    queue = get_queue()
    job = queue.enqueue(process_new_status, status_data)
    return {"job_id": job.id, "status": "queued"}
```

### From Background Jobs

Jobs can enqueue other jobs:

```python
from app.jobs.worker import get_queue
from app.jobs.tasks import analyze_and_maybe_report

def poll_admin_accounts():
    queue = get_queue()
    # Process accounts...
    if violation_detected:
        queue.enqueue(analyze_and_maybe_report, violation_data)
```

## Monitoring

### RQ Dashboard

Access the web dashboard at `http://localhost:9181` (development) or your configured URL (production).

Features:
- Real-time queue monitoring
- Job status and history
- Failed job details with stack traces
- Manual job retry/cancellation
- Worker status

### Job Management API

Query job status programmatically:

```bash
# List all jobs in default queue
curl http://localhost:8080/jobs/jobs?queue=default&status=queued

# Get specific job details
curl http://localhost:8080/jobs/jobs/{job_id}

# Manually trigger a job
curl -X POST http://localhost:8080/jobs/trigger/poll_admin_accounts
```

## Docker Services

### Development (`docker-compose up`)

Three RQ services run automatically:
- `worker`: Processes background jobs
- `scheduler`: Manages recurring jobs
- `rq-dashboard`: Web UI for monitoring (port 9181)

### Production

Update your deployment to include:

```yaml
services:
  worker:
    command: ["python", "-m", "app.jobs.worker"]
  
  scheduler:
    command: ["python", "-m", "app.jobs.scheduler"]
  
  rq-dashboard:
    command: ["rq-dashboard", "--redis-url", "${REDIS_URL}"]
    ports:
      - "9181:9181"
```

## Migration Checklist

For existing deployments migrating from Celery:

- [x] Update `requirements.txt` with RQ dependencies
- [x] Remove Celery and celery-sqlalchemy-scheduler
- [x] Update Docker Compose configuration
- [x] Remove `backend/app/tasks/celery_app.py`
- [x] Replace `.delay()` calls with `queue.enqueue()`
- [ ] Drain existing Celery queues before shutdown
- [ ] Update monitoring/alerting for RQ services
- [ ] Update deployment scripts

## Testing

RQ jobs are easier to test than Celery:

```python
def test_job():
    # Call job function directly - it's just a regular Python function
    result = poll_admin_accounts()
    assert result is not None

def test_job_enqueue():
    from app.jobs.worker import get_queue
    queue = get_queue()
    
    # Enqueue job
    job = queue.enqueue(poll_admin_accounts)
    
    # Check job was queued
    assert job.id is not None
    assert job.get_status() == 'queued'
```

## Troubleshooting

### Jobs Not Processing

Check worker is running:
```bash
docker-compose ps worker
docker-compose logs worker
```

### Scheduled Jobs Not Running

Check scheduler is running:
```bash
docker-compose ps scheduler
docker-compose logs scheduler
```

### Dashboard Not Accessible

Check dashboard service:
```bash
docker-compose ps rq-dashboard
docker-compose logs rq-dashboard
```

Ensure port 9181 is exposed and not blocked by firewall.

### Failed Jobs

View failed jobs in dashboard or via API:
```bash
curl http://localhost:8080/jobs/jobs?status=failed
```

Requeue failed jobs:
```bash
curl -X POST http://localhost:8080/jobs/jobs/{job_id}/requeue
```

## Performance Tuning

### Worker Concurrency

Run multiple workers for parallel processing:

```bash
# In docker-compose.yml
worker:
  deploy:
    replicas: 4  # Run 4 worker processes
```

### Job Timeouts

Set custom timeout for long-running jobs:

```python
queue.enqueue(
    long_running_task,
    timeout='10m',  # 10 minute timeout
    result_ttl=86400  # Keep result for 24 hours
)
```

### Queue Priority

Use separate queues for different priorities:

```python
high_priority = get_queue('high')
default_queue = get_queue('default')
low_priority = get_queue('low')

high_priority.enqueue(urgent_task)
low_priority.enqueue(background_cleanup)
```

## References

- [RQ Documentation](https://python-rq.org/)
- [RQ Scheduler Documentation](https://github.com/rq/rq-scheduler)
- [RQ Dashboard Documentation](https://github.com/Parallels/rq-dashboard)
