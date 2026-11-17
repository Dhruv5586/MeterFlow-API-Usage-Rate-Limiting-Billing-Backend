"""
Redis Client Manager & Connection Pool
--------------------------------------
Manages Redis connections for high-performance rate limiting, real-time counters,
and sliding window logs. Includes graceful in-memory FakeRedis fallback for offline
or local testing environments without an external Redis daemon.
"""

import logging
from typing import Optional
import redis
try:
    import fakeredis
    FAKEREDIS_AVAILABLE = True
except ImportError:
    FAKEREDIS_AVAILABLE = False

from app.core.config import settings

logger = logging.getLogger("meterflow.redis")

_redis_client: Optional[redis.Redis] = None
_is_fake_redis: bool = False


def init_redis_client() -> redis.Redis:
    """
    Initializes and returns the singleton Redis client.
    Attempts connection to the configured REDIS_URL first.
    If unavailable, falls back cleanly to FakeRedis for seamless offline operation.
    """
    global _redis_client, _is_fake_redis

    if _redis_client is not None:
        return _redis_client

    try:
        # Attempt connection to live Redis instance
        client = redis.Redis.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            socket_timeout=1.5,
            socket_connect_timeout=1.5,
        )
        client.ping()
        _redis_client = client
        _is_fake_redis = False
        logger.info(f"[✓] Connected to live Redis at {settings.REDIS_URL}")
        return _redis_client
    except Exception as exc:
        logger.warning(
            f"[!] Redis server at {settings.REDIS_URL} is unreachable ({exc}). "
            "Falling back to high-performance in-memory FakeRedis for rate limiting."
        )

        if FAKEREDIS_AVAILABLE:
            _redis_client = fakeredis.FakeRedis(decode_responses=True)
        else:
            # Re-raise if neither live Redis nor fakeredis is present
            raise exc

        _is_fake_redis = True
        return _redis_client


def get_redis_client() -> redis.Redis:
    """
    Returns the active Redis client, initializing it if necessary.
    """
    if _redis_client is None:
        return init_redis_client()
    return _redis_client


def check_redis_health() -> dict:
    """
    Health check helper reporting Redis status and backend mode.
    """
    client = get_redis_client()
    try:
        client.ping()
        return {
            "status": "healthy",
            "backend": "fakeredis_in_memory" if _is_fake_redis else "live_redis",
            "connected": True,
        }
    except Exception as exc:
        return {
            "status": "unhealthy",
            "backend": "none",
            "connected": False,
            "error": str(exc),
        }
