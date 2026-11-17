"""
Health Router
-------------
GET /api/v1/health: Verifies application and database connectivity.
"""

from datetime import datetime, timezone
from fastapi import APIRouter, status
from app.schemas.usage import HealthResponse
from app.core.database import check_database_health
from app.core.redis import check_redis_health
from app.core.config import settings

router = APIRouter(prefix="/health", tags=["System Health"])


@router.get(
    "",
    response_model=HealthResponse,
    status_code=status.HTTP_200_OK,
    summary="Application & Database Health Check",
    description="Returns service uptime status and verifies live PostgreSQL and Redis connections.",
)
def get_health() -> HealthResponse:
    try:
        is_db_connected = check_database_health()
    except Exception:
        is_db_connected = False

    redis_info = check_redis_health()

    return HealthResponse(
        status="healthy" if (is_db_connected and redis_info["connected"]) else "degraded",
        version=settings.APP_VERSION,
        server_time=datetime.now(timezone.utc),
        database_connected=is_db_connected,
        redis_connected=redis_info["connected"],
        rate_limiter_backend=redis_info.get("backend", "in_memory"),
    )
