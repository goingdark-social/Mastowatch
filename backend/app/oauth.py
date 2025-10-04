"""OAuth authentication utilities."""

import logging
from typing import Any

try:
    from authlib.integrations.starlette_client import OAuth

    AUTHLIB_AVAILABLE = True
except ImportError:
    AUTHLIB_AVAILABLE = False

    class OAuth:
        """Minimal stand-in for authlib's OAuth during tests."""

        def register(self, **kwargs):
            """No-op placeholder."""
            pass


from app.config import get_settings
from fastapi import Cookie, Depends, HTTPException, Request, Response, status
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class User(BaseModel):
    """Authenticated user information."""

    id: str
    username: str
    acct: str
    display_name: str
    is_admin: bool
    avatar_url: str | None = None


class OAuthConfig:
    """Handle OAuth setup and session token management."""

    def __init__(self, settings):
        self.settings = settings

        if not AUTHLIB_AVAILABLE:
            logger.warning("authlib not available - OAuth admin features will be unavailable")
            self.configured = False
            return

        self.oauth = OAuth()

        if not all(
            [
                settings.OAUTH_CLIENT_ID,
                settings.OAUTH_CLIENT_SECRET,
                settings.SESSION_SECRET_KEY,
            ]
        ):
            logger.warning("OAuth not fully configured - admin features will be unavailable")
            self.configured = False
            return

        self.configured = True

        self.oauth.register(
            name="mastodon",
            client_id=settings.OAUTH_CLIENT_ID,
            client_secret=settings.OAUTH_CLIENT_SECRET,
            authorize_url=f"{settings.INSTANCE_BASE}/oauth/authorize",
            access_token_url=f"{settings.INSTANCE_BASE}/oauth/token",
            client_kwargs={"scope": settings.OAUTH_SCOPE},
        )

        self.serializer = URLSafeTimedSerializer(settings.SESSION_SECRET_KEY)

    def create_session_token(self, user_data: dict[str, Any]) -> str:
        """Create a signed session token"""
        return self.serializer.dumps(user_data)

    def verify_session_token(self, token: str, max_age: int = None) -> dict[str, Any]:
        """Verify and decode session token"""
        if max_age is None:
            max_age = self.settings.SESSION_COOKIE_MAX_AGE

        try:
            return self.serializer.loads(token, max_age=max_age)
        except (BadSignature, SignatureExpired) as e:
            logger.debug(f"Invalid session token: {e}")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid or expired session",
            ) from e

    async def fetch_user_info(self, access_token: str) -> User | None:
        """Return user info from the Mastodon API."""

        try:
            from app.services.mastodon_service import mastodon_service

            data = await mastodon_service.verify_credentials(access_token)
            is_admin = False
            role_data = data.get("role")
            if role_data:
                try:
                    permissions = int(role_data.get("permissions", 0))
                    is_admin = bool(permissions & 1)
                except (ValueError, TypeError):
                    pass
                if not is_admin:
                    role_name = (role_data.get("name") or "").lower()
                    is_admin = role_name in ["admin", "moderator", "owner"]
            return User(
                id=data["id"],
                username=data["username"],
                acct=data["acct"],
                display_name=data.get("display_name") or data["username"],
                is_admin=is_admin,
                avatar_url=data.get("avatar"),
            )
        except Exception as e:
            logger.error(f"Error fetching user info: {e}")
            return None


# Global OAuth config instance
_oauth_config: OAuthConfig | None = None


def get_oauth_config() -> OAuthConfig:
    """Get the global OAuth configuration."""
    global _oauth_config
    if _oauth_config is None:
        _oauth_config = OAuthConfig(get_settings())
    return _oauth_config


def get_current_user(
    request: Request,
    session_cookie: str | None = Cookie(None, alias=None),
) -> User | None:
    """Return the user from the session cookie."""
    oauth_config = get_oauth_config()

    if not oauth_config.configured:
        return None

    settings = get_settings()
    cookie_name = settings.SESSION_COOKIE_NAME
    session_token = request.cookies.get(cookie_name)

    if not session_token:
        return None

    try:
        user_data = oauth_config.verify_session_token(session_token)
        return User(**user_data)
    except HTTPException:
        return None


current_user_dep = Depends(get_current_user)


def require_admin(current_user: User | None = current_user_dep) -> User:
    """Require an authenticated admin user."""
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def require_authenticated(current_user: User | None = current_user_dep) -> User:
    """Require any authenticated user."""
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    return current_user


def require_admin_hybrid(current_user: User | None = current_user_dep) -> User:
    """Require an authenticated admin user for hybrid auth."""
    if not current_user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentication required")
    if not current_user.is_admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin access required")
    return current_user


def _cookie_params(settings) -> dict[str, Any]:
    is_development = str(settings.INSTANCE_BASE).startswith("http://")
    same_site = "lax" if is_development else "strict"
    return {
        "path": "/",
        "httponly": True,
        "secure": not is_development,
        "samesite": same_site,
    }


def create_session_cookie(response: Response, user: User, settings) -> None:
    """Create and set session cookie."""
    oauth_config = get_oauth_config()
    session_token = oauth_config.create_session_token(user.model_dump())
    params = _cookie_params(settings)
    logger.info(
        f"Creating session cookie: name={settings.SESSION_COOKIE_NAME}, "
        f"secure={params['secure']}, samesite={params['samesite']}"
    )
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        max_age=settings.SESSION_COOKIE_MAX_AGE,
        **params,
    )


def clear_session_cookie(response: Response, settings) -> None:
    """Clear session cookie."""
    params = _cookie_params(settings)
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value="",
        max_age=0,
        **params,
    )
