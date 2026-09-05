"""
Shared middleware for request ID correlation and security headers.
"""
import hmac
import uuid
from collections.abc import Awaitable, Callable

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from app.config import get_settings

RequestResponseEndpoint = Callable[[Request], Awaitable[Response]]


class RequestIDMiddleware(BaseHTTPMiddleware):
    """Attach a request ID to every response and to the request state."""

    def __init__(self, app, header_name: str = "X-Request-ID") -> None:
        super().__init__(app)
        self.header_name = header_name

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        request_id = request.headers.get(self.header_name) or str(uuid.uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers[self.header_name] = request_id
        return response


class AdminGateMiddleware(BaseHTTPMiddleware):
    """
    Protect the /metrics endpoint with the admin API key when one is configured.

    Uses a middleware rather than a route dependency because the Prometheus
    instrumentator mounts /metrics outside the normal router dependency flow.
    """

    def __init__(self, app) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        settings = get_settings()
        if settings.admin_api_key and request.url.path == "/metrics":
            supplied = request.headers.get("X-Admin-Key", "")
            if not supplied:
                return JSONResponse(
                    status_code=401, content={"detail": "Missing X-Admin-Key header"}
                )
            if not hmac.compare_digest(supplied, settings.admin_api_key):
                return JSONResponse(
                    status_code=403, content={"detail": "Invalid admin credentials"}
                )
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Add a sensible set of security headers to every response."""

    def __init__(self, app) -> None:
        super().__init__(app)

    async def dispatch(
        self, request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        settings = get_settings()
        if settings.is_production:
            response.headers["Strict-Transport-Security"] = (
                "max-age=63072000; includeSubDomains; preload"
            )
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self'; "
            "img-src 'self' data:; base-uri 'self'; frame-ancestors 'none'"
        )
        response.headers["X-XSS-Protection"] = "1; mode=block"
        response.headers["Permissions-Policy"] = (
            "camera=(), microphone=(), geolocation=()"
        )
        return response
