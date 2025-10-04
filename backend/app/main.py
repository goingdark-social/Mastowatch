import hashlib
import hmac
import logging
import time
from datetime import datetime

import redis

# Import API routers
from app.api.analytics import router as analytics_router
from app.api.auth import router as auth_router
from app.api.config import router as config_router
from app.api.logs import router as logs_router
from app.api.rules import router as rules_router
from app.api.scanning import router as scanning_router
from app.config import get_settings
from app.db import SessionLocal
from app.logging_conf import setup_logging
from app.oauth import get_current_user, require_admin_hybrid


# For backward compatibility with tests
def get_current_user_hybrid(request=None):
    """Backward compatibility function for tests."""
    if request is None:
        # Import here to avoid circular imports
        from fastapi import Request

        request = Request(scope={"type": "http", "headers": []})
    return get_current_user(request)


# Make require_admin_hybrid available for test patching
require_admin_hybrid = require_admin_hybrid
from app.startup_validation import run_all_startup_validations
from app.tasks.jobs import process_new_report, process_new_status
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse
from fastapi.staticfiles import StaticFiles
from prometheus_client import CONTENT_TYPE_LATEST, generate_latest
from sqlalchemy import text
from starlette.middleware.sessions import SessionMiddleware

setup_logging()
logger = logging.getLogger(__name__)
settings = get_settings()

run_all_startup_validations()

app = FastAPI(title="MastoWatch", version=settings.VERSION)

# Add session middleware for OAuth2 flow (uses SESSION_SECRET_KEY from settings)
if settings.SESSION_SECRET_KEY:
    app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET_KEY)

# Register API routers
app.include_router(analytics_router)
app.include_router(rules_router)
app.include_router(config_router)
app.include_router(scanning_router)
app.include_router(auth_router)
app.include_router(logs_router)

if settings.CORS_ORIGINS:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

# Mount dashboard if present (built by the frontend build step)
try:
    app.mount("/dashboard", StaticFiles(directory="static/dashboard", html=True), name="dashboard")
except Exception:
    logging.info("Dashboard static assets not found; skipping mount.")


@app.get("/healthz", tags=["ops"])
def healthz():
    """Health check endpoint with comprehensive system status."""
    start_time = time.time()
    health_data = {
        "ok": True,
        "db_ok": False,
        "redis_ok": False,
        "dry_run": settings.DRY_RUN,
        "panic_stop": settings.PANIC_STOP,
        "batch_size": settings.BATCH_SIZE,
        "version": settings.VERSION,
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        # Test database connection
        try:
            with SessionLocal() as db:
                db.execute(text("SELECT 1"))
                health_data["db_ok"] = True
                logger.debug("Database health check passed")
        except Exception as e:
            logger.error("Database health check failed", extra={"error": str(e), "error_type": type(e).__name__})
            health_data["db_ok"] = False

        # Test Redis connection
        try:
            r = redis.from_url(settings.REDIS_URL)
            health_data["redis_ok"] = r.ping()
            logger.debug("Redis health check passed")
        except Exception as e:
            logger.error("Redis health check failed", extra={"error": str(e), "error_type": type(e).__name__})
            health_data["redis_ok"] = False

        health_data["ok"] = health_data["db_ok"] and health_data["redis_ok"]
        health_data["response_time_ms"] = round((time.time() - start_time) * 1000, 1)

        if not health_data["ok"]:
            logger.warning(
                "Health check failed",
                extra={
                    "db_ok": health_data["db_ok"],
                    "redis_ok": health_data["redis_ok"],
                    "response_time_ms": health_data["response_time_ms"],
                },
            )
            # Return 503 for failed health checks
            raise HTTPException(status_code=503, detail=health_data)

        return health_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error(
            "Health check endpoint failed with unexpected error",
            extra={
                "error": str(e),
                "error_type": type(e).__name__,
                "response_time_ms": round((time.time() - start_time) * 1000, 1),
            },
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "health_check_failed", "message": "Health check endpoint encountered an error"},
        )


@app.get("/livez", tags=["ops"])
def livez():
    """Liveness probe - always returns 200 if the process loop is alive."""
    return {"ok": True, "status": "alive", "timestamp": datetime.utcnow().isoformat()}


@app.get("/readyz", tags=["ops"])
def readyz():
    """Readiness probe - checks DB/Redis availability with fast timeout."""
    start_time = time.time()
    ready_data = {
        "ok": True,
        "db_ok": False,
        "redis_ok": False,
        "timestamp": datetime.utcnow().isoformat(),
    }

    try:
        # Test database connection with short timeout
        try:
            with SessionLocal() as db:
                # Use a simple query with timeout
                db.execute(text("SELECT 1"))
                ready_data["db_ok"] = True
        except Exception as e:
            logger.debug("Database readiness check failed", extra={"error": str(e)})
            ready_data["db_ok"] = False

        # Test Redis connection with short timeout
        try:
            r = redis.from_url(settings.REDIS_URL, socket_timeout=2)
            ready_data["redis_ok"] = r.ping()
        except Exception as e:
            logger.debug("Redis readiness check failed", extra={"error": str(e)})
            ready_data["redis_ok"] = False

        ready_data["ok"] = ready_data["db_ok"] and ready_data["redis_ok"]
        ready_data["response_time_ms"] = round((time.time() - start_time) * 1000, 1)

        if not ready_data["ok"]:
            raise HTTPException(status_code=503, detail=ready_data)

        return ready_data

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Readiness check failed", extra={"error": str(e), "error_type": type(e).__name__})
        raise HTTPException(
            status_code=503,
            detail={"error": "readiness_check_failed", "message": "Service not ready"},
        )


@app.get("/metrics", response_class=PlainTextResponse, tags=["ops"])
def metrics():
    return PlainTextResponse(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/webhooks/mastodon_events", tags=["webhooks"])
async def webhook_mastodon_events(request: Request):
    """Handle incoming Mastodon event webhooks with signature validation and event routing"""
    start_time = time.time()
    request_id = f"webhook_{int(start_time * 1000)}"

    try:
        body = await request.body()
        content_length = len(body)
        event_type = request.headers.get("X-Mastodon-Event", "unknown")

        logger.info(
            "Processing Mastodon webhook event",
            extra={
                "request_id": request_id,
                "event_type": event_type,
                "content_length": content_length,
                "source_ip": request.client.host if request.client else "unknown",
                "user_agent": request.headers.get("user-agent", "unknown"),
            },
        )

        # Validate webhook is configured
        if not settings.WEBHOOK_SECRET:
            logger.warning("Webhook received but WEBHOOK_SECRET not configured", extra={"request_id": request_id})
            raise HTTPException(
                status_code=503,
                detail={
                    "error": "webhook_not_configured",
                    "message": "Webhook secret not configured",
                    "request_id": request_id,
                },
            )

        # Validate signature
        sig_hdr = settings.WEBHOOK_SIG_HEADER
        provided = request.headers.get(sig_hdr, "")
        if not provided.startswith("sha256="):
            logger.warning(
                "Invalid signature header format",
                extra={
                    "request_id": request_id,
                    "signature_header": sig_hdr,
                    "provided_prefix": provided[:20] + "..." if len(provided) > 20 else provided,
                },
            )
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "invalid_signature_format",
                    "message": "Invalid signature header format",
                    "request_id": request_id,
                },
            )

        provided_hex = provided.split("=", 1)[1].strip()
        digest = hmac.new(settings.WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256).hexdigest()

        if not hmac.compare_digest(digest, provided_hex):
            logger.warning(
                "Webhook signature mismatch",
                extra={
                    "request_id": request_id,
                    "expected_signature_prefix": digest[:8] + "...",
                    "provided_signature_prefix": provided_hex[:8] + "...",
                },
            )
            raise HTTPException(
                status_code=401,
                detail={
                    "error": "signature_mismatch",
                    "message": "Webhook signature verification failed",
                    "request_id": request_id,
                },
            )

        # Parse payload
        try:
            payload = await request.json()
        except Exception as e:
            logger.error(
                "Failed to parse webhook JSON payload",
                extra={
                    "request_id": request_id,
                    "error": str(e),
                    "content_type": request.headers.get("content-type", "unknown"),
                },
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "error": "invalid_json_payload",
                    "message": "Failed to parse JSON payload",
                    "request_id": request_id,
                },
            )

        # Route events to appropriate Celery tasks
        task_id = None
        # Deduplication using Redis SETNX
        r = redis.from_url(settings.REDIS_URL)
        event_dedupe_key = f"webhook_dedupe:{event_type}:{payload.get('id', hashlib.sha256(body).hexdigest())}"
        if r.setnx(event_dedupe_key, "1"):
            r.expire(event_dedupe_key, 60)  # Deduplicate for 60 seconds
        else:
            logger.info(f"Duplicate webhook event received: {event_type}", extra={"request_id": request_id})
            return {"ok": True, "message": f"Duplicate event: {event_type}", "request_id": request_id}

        if event_type == "report.created":
            report_id = payload.get("report", {}).get("id")
            logger.info(f"Enqueuing report.created event for report ID: {report_id}", extra={"request_id": request_id})
            task = process_new_report.delay(payload)
            task_id = task.id
        elif event_type == "status.created":
            status_id = payload.get("status", {}).get("id")
            logger.info(f"Enqueuing status.created event for status ID: {status_id}", extra={"request_id": request_id})
            task = process_new_status.delay(payload)
            task_id = task.id
        else:
            logger.info(f"Received unhandled Mastodon event type: {event_type}", extra={"request_id": request_id})
            return {"ok": True, "message": f"Unhandled event type: {event_type}", "request_id": request_id}

        processing_time = time.time() - start_time
        logger.info(
            "Webhook processed successfully",
            extra={
                "request_id": request_id,
                "event_type": event_type,
                "content_length": content_length,
                "task_id": task_id,
                "processing_time_ms": round(processing_time * 1000, 1),
            },
        )

        return {
            "ok": True,
            "enqueued": True,
            "task_id": task_id,
            "event_type": event_type,
            "processing_time_ms": round(processing_time * 1000, 1),
            "request_id": request_id,
        }

    except HTTPException:
        raise
    except Exception as e:
        processing_time = time.time() - start_time
        logger.error(
            "Webhook processing failed with unexpected error",
            extra={
                "request_id": request_id,
                "error": str(e),
                "error_type": type(e).__name__,
                "processing_time_ms": round(processing_time * 1000, 1),
            },
        )
        raise HTTPException(
            status_code=500,
            detail={"error": "internal_server_error", "message": "Webhook processing failed", "request_id": request_id},
        )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
