"""Startup validation for critical environment variables and configuration."""

import logging
import sys

from app.config import get_settings
from app.services.mastodon_service import mastodon_service
from pydantic import ValidationError

logger = logging.getLogger(__name__)


def validate_startup_configuration() -> None:
    """Validate that all critical configuration is present and properly formatted.
    Fail fast with clear error messages if anything is missing or invalid.
    """
    errors: list[str] = []

    try:
        settings = get_settings()

        # Critical API tokens
        if not settings.MASTODON_CLIENT_SECRET or settings.MASTODON_CLIENT_SECRET == "REPLACE_WITH_BOT_ACCESS_TOKEN":
            errors.append("MASTODON_CLIENT_SECRET is missing or contains placeholder value")

        if not settings.MASTODON_CLIENT_SECRET or settings.MASTODON_CLIENT_SECRET == "REPLACE_WITH_ADMIN_ACCESS_TOKEN":
            errors.append("MASTODON_CLIENT_SECRET is missing or contains placeholder value")

        # Database and Redis connectivity
        if not settings.DATABASE_URL:
            errors.append("DATABASE_URL is required")
        elif "REPLACE" in settings.DATABASE_URL.upper():
            errors.append("DATABASE_URL contains placeholder values")

        if not settings.REDIS_URL:
            errors.append("REDIS_URL is required")
        elif "REPLACE" in settings.REDIS_URL.upper():
            errors.append("REDIS_URL contains placeholder values")

        # Instance configuration
        if not settings.INSTANCE_BASE:
            errors.append("INSTANCE_BASE is required")
        elif str(settings.INSTANCE_BASE) == "https://your.instance":
            errors.append("INSTANCE_BASE contains placeholder value")

        # API security
        if settings.API_KEY == "REPLACE_ME":
            errors.append("API_KEY contains placeholder value (set to secure value or null to disable)")

        # Webhook security (if webhooks enabled)
        if settings.WEBHOOK_SECRET == "REPLACE_ME":
            errors.append("WEBHOOK_SECRET contains placeholder value (set to secure value or null to disable webhooks)")

        # Validate numeric ranges
        if settings.MAX_PAGES_PER_POLL < 1:
            errors.append("MAX_PAGES_PER_POLL must be >= 1")

        if settings.MAX_STATUSES_TO_FETCH < 1:
            errors.append("MAX_STATUSES_TO_FETCH must be >= 1")

        if settings.BATCH_SIZE < 1:
            errors.append("BATCH_SIZE must be >= 1")

        # Validate report category
        valid_categories = {"spam", "violation", "legal", "other"}
        if settings.REPORT_CATEGORY_DEFAULT not in valid_categories:
            errors.append(f"REPORT_CATEGORY_DEFAULT must be one of: {valid_categories}")

    except ValidationError as e:
        errors.append(f"Configuration validation failed: {e}")
    except Exception as e:
        errors.append(f"Unexpected error during configuration validation: {e}")

    if errors:
        logger.error("STARTUP VALIDATION FAILED:")
        for error in errors:
            logger.error(f"  - {error}")
        logger.error("Please fix the above configuration issues before starting the application.")
        sys.exit(1)
    else:
        logger.info("✓ Startup configuration validation passed")


def validate_database_connection() -> None:
    """Test database connectivity and migration status."""
    try:
        from app.db import SessionLocal
        from sqlalchemy import text

        with SessionLocal() as db:
            # Test basic connectivity
            result = db.execute(text("SELECT 1")).scalar()
            if result != 1:
                raise Exception("Database connectivity test failed")

            # Check if migrations table exists (indicates Alembic is set up)
            try:
                db.execute(text("SELECT version_num FROM alembic_version LIMIT 1"))
                logger.info("✓ Database connected and migrations table found")
            except Exception:
                logger.warning("⚠ Database connected but no migrations table found - run 'alembic upgrade head'")

    except Exception as e:
        logger.error(f"Database validation failed: {e}")
        sys.exit(1)


def validate_redis_connection() -> None:
    """Test Redis connectivity."""
    try:
        import redis
        from app.config import get_settings

        settings = get_settings()
        r = redis.from_url(settings.REDIS_URL)

        if not r.ping():
            raise Exception("Redis ping failed")

        logger.info("✓ Redis connection validated")

    except Exception as e:
        logger.error(f"Redis validation failed: {e}")
        sys.exit(1)


def validate_mastodon_version() -> None:
    """Fetches Mastodon instance version and validates it against MIN_MASTODON_VERSION."""
    settings = get_settings()
    try:
        # Use mastodon.py's instance() method
        instance_info = mastodon_service.get_instance_info_sync()
        current_version = instance_info.get("version")
        if not current_version:
            raise ValueError("Could not find version in instance info")

        logger.info(f"Mastodon instance version: {current_version}")

        import re

        version_match = re.match(r"^(\d+)\.(\d+)\.(\d+)", current_version)
        if not version_match:
            raise ValueError(f"Could not parse version number from: {current_version}")

        current_parts = [int(version_match.group(1)), int(version_match.group(2)), int(version_match.group(3))]
        min_version = settings.MIN_MASTODON_VERSION
        min_parts = [int(x) for x in min_version.split(".")[:3]]

        if current_parts < min_parts:
            logger.error(
                f"UNSUPPORTED MASTODON VERSION: MastoWatch requires at least version {min_version}, "
                f"but found {current_version}. Please upgrade your Mastodon instance."
            )
            sys.exit(1)
        else:
            logger.info(f"✓ Mastodon instance version {current_version} is supported (min: {min_version})")

    except Exception as e:
        logger.error(f"Failed to validate Mastodon instance version: {e}")
        sys.exit(1)


def run_all_startup_validations() -> None:
    """Run all startup validations. Call this early in application startup.
    Can be disabled by setting SKIP_STARTUP_VALIDATION environment variable.
    """
    import os

    if os.getenv("SKIP_STARTUP_VALIDATION"):
        logger.info("Startup validations skipped (SKIP_STARTUP_VALIDATION set)")
        return

    logger.info("Running startup validations...")
    validate_startup_configuration()
    validate_database_connection()
    validate_redis_connection()

    validate_mastodon_version()

    logger.info("✓ All startup validations passed")
