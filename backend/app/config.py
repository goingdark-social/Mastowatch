"""Application configuration settings."""

from functools import lru_cache

from pydantic import AnyHttpUrl, AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    """Runtime configuration loaded from environment."""

    VERSION: str = APP_VERSION

    # Required connection details
    INSTANCE_BASE: AnyUrl
    DATABASE_URL: str = Field(..., min_length=1)
    REDIS_URL: str = Field(..., min_length=1)
    UI_ORIGIN: AnyHttpUrl

    # Auth tokens / credentials
    MASTODON_CLIENT_SECRET: str = Field(..., min_length=1)

    # Core runtime defaults (aligned with tests)
    DRY_RUN: bool = True
    MAX_PAGES_PER_POLL: int = 3
    MAX_STATUSES_TO_FETCH: int = 5
    BATCH_SIZE: int = 20
    USER_AGENT: str = f"MastoWatch/{APP_VERSION} (+moderation-sidecar)"
    HTTP_TIMEOUT: float = 30.0
    RULE_CACHE_TTL: int = 60

    # Reporting behavior
    REPORT_CATEGORY_DEFAULT: str = "spam"
    FORWARD_REMOTE_REPORTS: bool = False
    POLICY_VERSION: str = "v1"

    # Ops toggles
    PANIC_STOP: bool = False
    API_KEY: str | None = None

    # Webhooks (Mastodon API v2 compliant)
    WEBHOOK_SECRET: str | None = None
    WEBHOOK_SIG_HEADER: str = "X-Hub-Signature"

    # Slack notifications
    SLACK_WEBHOOKS: dict[str, str] = Field(default_factory=dict)

    # CORS for dashboard if served separately (not required when embedded)
    CORS_ORIGINS: list[str] = Field(default_factory=list)

    # OAuth configuration for admin login
    MASTODON_CLIENT_KEY: str | None = None
    OAUTH_REDIRECT_URI: str | None = None
    OAUTH_SCOPE: str = "read write follow admin:read admin:read:accounts admin:write:accounts"
    OAUTH_POPUP_REDIRECT_URI: str | None = None

    SESSION_SECRET_KEY: str | None = None
    SESSION_COOKIE_NAME: str = "mastowatch_session"
    SESSION_COOKIE_MAX_AGE: int = 86400

    MIN_MASTODON_VERSION: str = "4.0.0"
    POLL_ADMIN_ACCOUNTS_INTERVAL: int = 30
    POLL_ADMIN_ACCOUNTS_LOCAL_INTERVAL: int = 30
    QUEUE_STATS_INTERVAL: int = 15
    CONTENT_CACHE_TTL: int = 24  # Hours to cache content scans

    # Compatibility aliases
    @property
    def MASTODON_ACCESS_TOKEN(self) -> str:
        """Maintain backwards compatibility for older imports."""
        return self.MASTODON_CLIENT_SECRET

    @property
    def OAUTH_CLIENT_ID(self) -> str | None:
        """Expose Mastodon client ID via the legacy alias."""
        return self.MASTODON_CLIENT_KEY

    @property
    def OAUTH_CLIENT_SECRET(self) -> str | None:
        """Expose Mastodon client secret via the legacy alias."""
        return self.MASTODON_CLIENT_SECRET

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",
    )


@lru_cache
def get_settings():
    """Return Settings instance."""
    return Settings()
