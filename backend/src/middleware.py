from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address, default_limits=["100/minute"])


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """Adds the OWASP-recommended security headers to every response."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
        # img-src needs 'data:' for the boarding-pass QR code (rendered as a data URI);
        # style-src needs 'unsafe-inline' for CRA's injected inline styles.
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; connect-src 'self' https:"
        )
        response.headers["X-XSS-Protection"] = "1; mode=block"
        return response
