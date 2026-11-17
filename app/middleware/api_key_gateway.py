"""
API Gateway Header Verification & High-Performance Rate Limiting Middleware
----------------------------------------------------------------------------
1. Enforces X-API-Key authentication on API Gateway routes (/api/v1/gateway/*).
2. Performs distributed Rate Limiting via Redis (Sliding Window / Token Bucket).
3. Evaluates monthly consumption against plan quotas (Soft vs. Hard limits).
4. Injects RFC-compliant rate-limit headers (X-RateLimit-Limit, Remaining, Reset).
5. Returns HTTP 429 (Too Many Requests) with Retry-After when thresholds are exceeded.
"""

import logging
from datetime import datetime, timezone
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.status import HTTP_401_UNAUTHORIZED, HTTP_429_TOO_MANY_REQUESTS

from app.core.database import SessionLocal
from app.core.security import hash_api_key
from app.repositories.api_key_repository import APIKeyRepository
from app.services.rate_limiter import RateLimiter
from app.services.quota_service import QuotaService

logger = logging.getLogger("meterflow.gateway")

# Protected URL path prefixes that strictly require X-API-Key and Rate Limiting
GATEWAY_PATH_PREFIXES = (
    "/api/v1/gateway",
)


class APIKeyGatewayMiddleware(BaseHTTPMiddleware):
    def __init__(self, app):
        super().__init__(app)
        self.rate_limiter = RateLimiter()

    async def dispatch(self, request: Request, call_next):
        path = request.url.path

        # Check if this route is designated as an API Gateway protected endpoint
        is_gateway_route = any(path.startswith(prefix) for prefix in GATEWAY_PATH_PREFIXES)
        api_key_header = request.headers.get("X-API-Key")

        # If it's a gateway route or an explicit X-API-Key was supplied:
        if is_gateway_route or api_key_header is not None:
            if not api_key_header or not api_key_header.strip():
                if is_gateway_route:
                    return JSONResponse(
                        status_code=HTTP_401_UNAUTHORIZED,
                        headers={"WWW-Authenticate": "ApiKey"},
                        content={
                            "error": "Unauthorized",
                            "message": "Missing required 'X-API-Key' authentication header for API Gateway.",
                            "path": path,
                        },
                    )
                # If non-gateway route and header is empty, let it pass to other auth mechanisms
                return await call_next(request)

            # Validate API Key against database
            db = SessionLocal()
            try:
                key_hash = hash_api_key(api_key_header)
                repo = APIKeyRepository(db)
                api_key = repo.get_by_hash(key_hash)

                if not api_key:
                    return JSONResponse(
                        status_code=HTTP_401_UNAUTHORIZED,
                        headers={"WWW-Authenticate": "ApiKey"},
                        content={
                            "error": "Unauthorized",
                            "message": "Invalid API key provided.",
                            "path": path,
                        },
                    )

                now = datetime.now(timezone.utc)

                # 1. Check if revoked
                if api_key.revoked_at is not None:
                    return JSONResponse(
                        status_code=HTTP_401_UNAUTHORIZED,
                        content={
                            "error": "Unauthorized",
                            "message": f"API key was revoked on {api_key.revoked_at.isoformat()} and can no longer be used.",
                            "path": path,
                        },
                    )

                # 2. Check if expired
                if api_key.expires_at is not None and api_key.expires_at <= now:
                    return JSONResponse(
                        status_code=HTTP_401_UNAUTHORIZED,
                        content={
                            "error": "Unauthorized",
                            "message": f"API key expired on {api_key.expires_at.isoformat()}.",
                            "path": path,
                        },
                    )

                # 3. Check if user account is active
                if not api_key.user or api_key.user.status != "active":
                    return JSONResponse(
                        status_code=HTTP_401_UNAUTHORIZED,
                        content={
                            "error": "Unauthorized",
                            "message": "The tenant account associated with this API key is inactive or suspended.",
                            "path": path,
                        },
                    )

                # 4. Quota Resolution (Monthly Limit)
                quota_service = QuotaService(db)
                quota_eval = quota_service.evaluate(api_key.user)

                if quota_eval.is_quota_exceeded:
                    return JSONResponse(
                        status_code=HTTP_429_TOO_MANY_REQUESTS,
                        headers={
                            "Retry-After": "86400",
                            "X-RateLimit-Limit": str(quota_eval.monthly_quota_limit),
                            "X-RateLimit-Remaining": "0",
                            "X-RateLimit-Reset": "86400",
                        },
                        content={
                            "error": "Too Many Requests",
                            "message": (
                                f"Monthly quota limit of {quota_eval.monthly_quota_limit:,} requests reached "
                                f"for plan '{quota_eval.plan_code.upper()}'. Please upgrade your plan."
                            ),
                            "limit": quota_eval.monthly_quota_limit,
                            "remaining": 0,
                            "reset_seconds": 86400,
                            "path": path,
                        },
                    )

                # 5. High-Performance Rate Limiting (Per-Minute Rolling Window)
                rate_result = self.rate_limiter.check(
                    identifier=f"key:{api_key.id}",
                    limit=quota_eval.rate_limit_per_minute,
                    window_seconds=60,
                )

                if not rate_result.allowed:
                    return JSONResponse(
                        status_code=HTTP_429_TOO_MANY_REQUESTS,
                        headers=rate_result.headers,
                        content={
                            "error": "Too Many Requests",
                            "message": (
                                f"Rate limit of {rate_result.limit} requests per minute exceeded. "
                                f"Please retry in {rate_result.retry_after} seconds."
                            ),
                            "limit": rate_result.limit,
                            "remaining": rate_result.remaining,
                            "reset_seconds": rate_result.reset_seconds,
                            "path": path,
                        },
                    )

                # Attach authenticated key, user, and rate limit info to request state
                request.state.api_key = api_key
                request.state.user = api_key.user
                request.state.rate_result = rate_result

                # Touch last_used_at
                repo.touch_last_used(api_key.id)
                db.commit()

            except Exception as exc:
                logger.error(f"Error during API key gateway verification: {exc}", exc_info=True)
                db.rollback()
                return JSONResponse(
                    status_code=HTTP_401_UNAUTHORIZED,
                    content={
                        "error": "Unauthorized",
                        "message": "API key verification failed due to internal error.",
                        "path": path,
                    },
                )
            finally:
                db.close()

            # Execute downstream request
            response = await call_next(request)

            # Injected custom rate-limiting and quota warning headers
            if hasattr(request.state, "rate_result"):
                res: RateLimiter = request.state.rate_result
                for k, v in res.headers.items():
                    response.headers[k] = v

            if hasattr(request.state, "user") and 'quota_eval' in locals() and quota_eval.is_soft_warning:
                response.headers["X-Quota-Warning"] = f"Usage reached {quota_eval.current_monthly_usage:,} / {quota_eval.monthly_quota_limit:,} requests (>=80%)"

            return response

        return await call_next(request)
