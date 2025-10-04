"""Application configuration settings."""

from functools import lru_cache

from pydantic import AnyUrl, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

APP_VERSION = "0.1.0"


class Settings(BaseSettings):
    """Runtime configuration loaded from environment."""

    VERSION: str = APP_VERSION
    INSTANCE_BASE: AnyUrl
    MASTODON_ACCESS_TOKEN: str = Field(..., min_length=1)
    DATABASE_URL: str = Field(..., min_length=1)
    REDIS_URL: str = Field(..., min_length=1)
    DRY_RUN: bool = True
    MAX_PAGES_PER_POLL: int = 3
    USER_AGENT: str = f"MastoWatch/{APP_VERSION} (+moderation-sidecar)"
    HTTP_TIMEOUT: float = 30.0
    MAX_STATUSES_TO_FETCH: int = 5
    BATCH_SIZE: int = 20
    HTTP_TIMEOUT: float = 30.0
    RULE_CACHE_TTL: int = 60

    # Reporting behavior
    REPORT_CATEGORY_DEFAULT: str = "spam"  # spam | violation | legal | other
    FORWARD_REMOTE_REPORTS: bool = False
    POLICY_VERSION: str = "v1"

    # Ops toggles
    PANIC_STOP: bool = False
    API_KEY: str | None = None

    # Webhooks (Mastodon API v2 compliant)
    WEBHOOK_SECRET: str | None = None
    WEBHOOK_SIG_HEADER: str = "X-Hub-Signature"  # Mastodon uses X-Hub-Signature (not X-Hub-Signature-256)

    # Slack notifications
    SLACK_WEBHOOKS: dict[str, str] = Field(default_factory=dict)

    # CORS for dashboard if served separately (not required when embedded)
    CORS_ORIGINS: list[str] = []

    # OAuth Configuration for admin login (uses same Mastodon app credentials)
    MASTODON_CLIENT_KEY: str | None = None
    MASTODON_CLIENT_SECRET: str | None = None

    # OAuth aliases (used by auth endpoints)
    @property
    def OAUTH_CLIENT_ID(self) -> str | None:
        """Alias for MASTODON_CLIENT_KEY (used by auth endpoints)."""
        return self.MASTODON_CLIENT_KEY

    @property
    def OAUTH_CLIENT_SECRET(self) -> str | None:
        """Alias for MASTODON_CLIENT_SECRET (used by auth endpoints)."""
        return self.MASTODON_CLIENT_SECRET

    OAUTH_REDIRECT_URI: str | None = None
    OAUTH_SCOPE: str = "read write follow admin:read admin:read:accounts admin:write:accounts"
    OAUTH_POPUP_REDIRECT_URI: str | None = None
    SESSION_SECRET_KEY: str | None = None
    SESSION_COOKIE_NAME: str = "mastowatch_session"
    SESSION_COOKIE_MAX_AGE: int = 86400  # 24 hours in seconds

    UI_ORIGIN: str = Field(..., min_length=1)

    MIN_MASTODON_VERSION: str = "4.0.0"
    POLL_ADMIN_ACCOUNTS_INTERVAL: int = 30
    POLL_ADMIN_ACCOUNTS_LOCAL_INTERVAL: int = 30
    QUEUE_STATS_INTERVAL: int = 15

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="ignore",  # Allow extra env vars without validation errors
    )


@lru_cache
def get_settings():
    """Return Settings instance."""
    return Settings()
