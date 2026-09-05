"""
Authentication helpers for protecting admin endpoints.
"""
import hmac

from fastapi import HTTPException, Request, status

from app.config import get_settings


def _is_admin(request: Request) -> bool:
    """Return True if the request carries a valid admin API key."""
    settings = get_settings()
    if not settings.admin_api_key:
        # No key configured: this is a non-production convenience, so allow.
        return True
    supplied = request.headers.get("X-Admin-Key", "")
    return hmac.compare_digest(supplied, settings.admin_api_key)


def require_admin(request: Request) -> None:
    """Raise 401/403 if the request is not authorized as an admin."""
    settings = get_settings()
    supplied = request.headers.get("X-Admin-Key", "")
    if not supplied and settings.admin_api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Admin-Key header",
        )
    if not _is_admin(request):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or expired admin credentials",
        )
