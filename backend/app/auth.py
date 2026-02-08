"""Authentication and authorization utilities."""

from app.config import get_settings
from fastapi import Header, HTTPException, status


def require_api_key(x_api_key: str | None = Header(default=None, alias="X-API-Key")):
    """Validate X-API-Key header for protected API endpoints."""
    settings = get_settings()
    if not settings.API_KEY:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail="API_KEY not configured")
    if x_api_key != settings.API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
    return True
