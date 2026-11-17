"""
Request Logging Middleware
--------------------------
Logs HTTP method, path, status code, and latency in milliseconds.
Appends an X-Process-Time header to all HTTP responses.
"""

import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("meterflow.access")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        start_time = time.perf_counter()
        
        # Process request
        response = await call_next(request)
        
        # Calculate latency
        process_time_ms = (time.perf_counter() - start_time) * 1000
        response.headers["X-Process-Time"] = f"{process_time_ms:.2f}ms"
        
        # Log request summary
        logger.info(
            f"{request.method} {request.url.path} "
            f"-> Status: {response.status_code} ({process_time_ms:.2f}ms)"
        )
        return response
