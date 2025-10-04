"""Database-backed configuration helpers."""

from typing import Any

from app.db import SessionLocal
from app.models import Config


class ConfigService:
    """CRUD operations for application configuration."""

    def get_config(self, key: str) -> Any | None:
        """Return configuration value for key."""
        with SessionLocal() as session:
            row = session.get(Config, key)
            return row.value if row else None

    def set_flag(self, key: str, enabled: bool, updated_by: str | None = None) -> dict[str, bool]:
        """Store boolean flag in configuration."""
        with SessionLocal() as session:
            config = session.get(Config, key)
            if config:
                config.value = {"enabled": enabled}
                config.updated_by = updated_by
            else:
                session.add(Config(key=key, value={"enabled": enabled}, updated_by=updated_by))
            session.commit()
            return {"enabled": enabled}

    def set_threshold(self, key: str, threshold: float, updated_by: str | None = None) -> dict[str, float]:
        """Store numeric threshold in configuration."""
        with SessionLocal() as session:
            config = session.get(Config, key)
            if config:
                config.value = {"threshold": threshold}
                config.updated_by = updated_by
            else:
                session.add(Config(key=key, value={"threshold": threshold}, updated_by=updated_by))
            session.commit()
            return {"threshold": threshold}

    def set_automod_config(
        self,
        *,
        dry_run_override: bool | None = None,
        default_action: str | None = None,
        defederation_threshold: int | None = None,
        updated_by: str | None = None,
    ) -> dict[str, Any]:
        """Update AutoMod settings."""
        with SessionLocal() as session:
            config = session.get(Config, "automod")
            value = config.value if config else {}
            if dry_run_override is not None:
                value["dry_run_override"] = dry_run_override
            if default_action is not None:
                value["default_action"] = default_action
            if defederation_threshold is not None:
                value["defederation_threshold"] = defederation_threshold
            if config:
                config.value = value
                config.updated_by = updated_by
            else:
                session.add(Config(key="automod", value=value, updated_by=updated_by))
            session.commit()
            return value


config_service = ConfigService()


def get_config_service() -> ConfigService:
    """Return ConfigService instance."""
    return config_service
