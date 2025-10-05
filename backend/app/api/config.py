"""Configuration management API routes."""

from typing import Any

from app.auth import require_api_key
from app.config import get_settings
from app.oauth import User, require_admin_hybrid
from app.services.config_service import ConfigService, get_config_service
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

router = APIRouter()

api_key_dep = Depends(require_api_key)
admin_dep = Depends(require_admin_hybrid)
service_dep = Depends(get_config_service)
MAX_THRESHOLD = 10


class AutoModSettings(BaseModel):
    """AutoMod configuration options."""

    dry_run_override: bool | None = Field(default=None)
    default_action: str | None = Field(default=None)
    defederation_threshold: int | None = Field(default=None)


@router.get("/config", response_model=dict[str, Any])
def get_app_config(
    user: User = api_key_dep,
    service: ConfigService = service_dep,
):
    """Return non-sensitive configuration values."""
    settings = get_settings()
    allowed = {
        "VERSION",
        "DRY_RUN",
        "PANIC_STOP",
        "REPORT_CATEGORY_DEFAULT",
        "FORWARD_REMOTE_REPORTS",
        "MAX_PAGES_PER_POLL",
        "MAX_STATUSES_TO_FETCH",
    }
    config: dict[str, Any] = {k: getattr(settings, k) for k in allowed}
    panic_stop = service.get_config("panic_stop")
    if panic_stop:
        config["PANIC_STOP"] = panic_stop.get("enabled", config["PANIC_STOP"])
    dry_run = service.get_config("dry_run")
    if dry_run:
        config["DRY_RUN"] = dry_run.get("enabled", config["DRY_RUN"])
    report_threshold = service.get_config("report_threshold")
    if report_threshold:
        config["REPORT_THRESHOLD"] = report_threshold.get("threshold")
    return config


@router.post("/config/panic_stop", status_code=status.HTTP_200_OK)
def set_panic_stop(
    enable: bool,
    user: User = admin_dep,
    service: ConfigService = service_dep,
):
    """Toggle panic stop flag."""
    service.set_flag("panic_stop", enable, updated_by=user.username)
    return {"panic_stop": enable}


@router.post("/config/dry_run", tags=["ops"])
def set_dry_run_mode(
    enable: bool,
    user: User = admin_dep,
    service: ConfigService = service_dep,
):
    """Toggle dry run mode."""
    service.set_flag("dry_run", enable, updated_by=user.username)
    return {"dry_run": enable}


@router.post("/config/report_threshold", tags=["ops"])
def set_report_threshold(
    threshold: float,
    user: User = admin_dep,
    service: ConfigService = service_dep,
):
    """Update report threshold."""
    if threshold < 0 or threshold > MAX_THRESHOLD:
        raise HTTPException(status_code=400, detail="Threshold must be between 0 and 10")
    service.set_threshold("report_threshold", threshold, updated_by=user.username)
    return {"report_threshold": threshold}


@router.get("/config/automod", tags=["ops"], response_model=dict[str, Any])
def get_automod_config(
    user: User = admin_dep,
    service: ConfigService = service_dep,
):
    """Return current AutoMod settings."""
    config = service.get_config("automod") or {}
    return {
        "dry_run_override": config.get("dry_run_override"),
        "default_action": config.get("default_action"),
        "defederation_threshold": config.get("defederation_threshold"),
    }


@router.post("/config/automod", tags=["ops"], response_model=dict[str, Any])
def set_automod_config(
    settings: AutoModSettings,
    user: User = admin_dep,
    service: ConfigService = service_dep,
):
    """Update AutoMod settings."""
    allowed_actions = {"report", "suspend", "ignore"}  # Add/modify as needed
    if settings.defederation_threshold is not None and settings.defederation_threshold < 0:
        raise HTTPException(status_code=400, detail="Threshold must be non-negative")
    if settings.default_action is not None and settings.default_action not in allowed_actions:
        raise HTTPException(status_code=400, detail=f"default_action must be one of {sorted(allowed_actions)}")
    return service.set_automod_config(
        dry_run_override=settings.dry_run_override,
        default_action=settings.default_action,
        defederation_threshold=settings.defederation_threshold,
        updated_by=user.username,
    )
