"""
Security Headers Middleware
---------------------------
Injects OWASP-recommended security headers into all HTTP responses.
- X-Content-Type-Options: nosniff
- X-Frame-Options: DENY
- Referrer-Policy: strict-origin-when-cross-origin
- Content-Security-Policy: default-src 'none'; frame-ancestors 'none'
- Strict-Transport-Security: max-age=31536000; includeSubDomains (when HTTPS is active/enabled)
"""

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from app.core.config import settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response: Response = await call_next(request)

        # 1. Prevent MIME-type sniffing
        response.headers["X-Content-Type-Options"] = "nosniff"

        # 2. Clickjacking protection
        response.headers["X-Frame-Options"] = "DENY"

        # 3. Referrer leakage protection
        response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

        # 4. Restrict resource loading & framing
        path = request.url.path
        if path.startswith("/docs") or path.startswith("/redoc") or path == "/openapi.json":
            # Allow Swagger UI & ReDoc CDNs to load styling, scripts and favicons
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; "
                "img-src 'self' data: https://fastapi.tiangolo.com; "
                "style-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; "
                "frame-ancestors 'none'"
            )
        else:
            response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"

        # 5. HSTS (only when HTTPS deployment is enabled or request is over HTTPS)
        is_https = (
            request.url.scheme == "https"
            or request.headers.get("x-forwarded-proto") == "https"
            or getattr(settings, "ENABLE_HSTS", False)
        )
        if is_https:
            response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

        return response
