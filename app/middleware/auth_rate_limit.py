"""
Authentication Route IP Rate Limiting Middleware
-------------------------------------------------
Enforces strict client IP rate limiting on public authentication endpoints:
- POST /api/v1/auth/login
- POST /api/v1/auth/register

Default threshold: 10 requests / minute per client IP.
Safe proxy verification prevents IP spoofing via arbitrary X-Forwarded-For headers.
Emits HTTP 429 Too Many Requests with standard Retry-After and X-RateLimit headers.
"""

import logging
from typing import List, Optional
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_429_TOO_MANY_REQUESTS

from app.core.config import settings
from app.services.rate_limiter import RateLimiter

logger = logging.getLogger("meterflow.security.auth_rate_limit")

AUTH_THROTTLED_PATHS = {
    "/api/v1/auth/login",
    "/api/v1/auth/register",
}


def get_trusted_client_ip(request: Request, trusted_proxies: Optional[List[str]] = None) -> str:
    """
    Safely resolves client IP address.
    Only inspects X-Forwarded-For if the immediate peer client.host is explicitly
    listed in trusted_proxies. Arbitrary/untrusted clients providing forged
    forwarding headers are ignored to prevent IP spoofing attacks.
    """
    peer_ip = request.client.host if request.client else "127.0.0.1"

    if trusted_proxies and peer_ip in trusted_proxies:
        forwarded_header = request.headers.get("x-forwarded-for")
        if forwarded_header:
            # X-Forwarded-For: client, proxy1, proxy2
            ips = [ip.strip() for ip in forwarded_header.split(",") if ip.strip()]
            if ips:
                return ips[0]

    return peer_ip


class AuthRateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, rate_limiter: Optional[RateLimiter] = None):
        super().__init__(app)
        self.rate_limiter = rate_limiter or RateLimiter()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path
        method = request.method.upper()

        if method == "POST" and path in AUTH_THROTTLED_PATHS:
            trusted_proxies = settings.trusted_proxies_list
            client_ip = get_trusted_client_ip(request, trusted_proxies)

            identifier = f"auth:ip:{client_ip}"
            limit = getattr(settings, "AUTH_RATE_LIMIT_PER_MINUTE", 10)
            window_seconds = 60

            rate_result = self.rate_limiter.check(
                identifier=identifier,
                limit=limit,
                window_seconds=window_seconds,
            )

            if not rate_result.allowed:
                logger.warning(
                    f"Authentication rate limit exceeded for IP {client_ip} on {method} {path} "
                    f"(limit: {limit}/min, retry after: {rate_result.retry_after}s)"
                )
                return JSONResponse(
                    status_code=HTTP_429_TOO_MANY_REQUESTS,
                    headers=rate_result.headers,
                    content={
                        "error": "Too Many Requests",
                        "message": (
                            f"Too many authentication requests from this IP address. "
                            f"Rate limit of {limit} requests per minute exceeded. "
                            f"Please retry in {rate_result.retry_after} seconds."
                        ),
                        "limit": rate_result.limit,
                        "remaining": rate_result.remaining,
                        "reset_seconds": rate_result.reset_seconds,
                        "path": path,
                    },
                )

            # Allowed - proceed and attach rate limit headers
            response = await call_next(request)
            for k, v in rate_result.headers.items():
                response.headers[k] = v
            return response

        return await call_next(request)
