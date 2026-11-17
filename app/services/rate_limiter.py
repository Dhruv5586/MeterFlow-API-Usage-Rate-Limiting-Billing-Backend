"""
High-Performance Rate Limiting Engine
-------------------------------------
Implements two algorithms:
1. Sliding Window Log (precise, eliminates boundary-burst exploits via Redis ZSET).
2. Token Bucket (smooth rate with burst capacity via atomic token replenishment).

Provides standard RFC-compliant rate limit metrics for HTTP headers:
- X-RateLimit-Limit
- X-RateLimit-Remaining
- X-RateLimit-Reset
- Retry-After
"""

import time
import uuid
from dataclasses import dataclass
from typing import Tuple, Optional
import redis

from app.core.config import settings
from app.core.redis import get_redis_client


@dataclass
class RateLimitResult:
    allowed: bool
    limit: int
    remaining: int
    reset_seconds: int
    retry_after: int

    @property
    def headers(self) -> dict:
        """Returns standard HTTP rate-limiting headers."""
        h = {
            "X-RateLimit-Limit": str(self.limit),
            "X-RateLimit-Remaining": str(max(0, self.remaining)),
            "X-RateLimit-Reset": str(max(1, self.reset_seconds)),
        }
        if not self.allowed:
            h["Retry-After"] = str(max(1, self.retry_after))
        return h


# -----------------------------------------------------------------------------
# 1. Sliding Window Log Algorithm (Atomic Lua Script)
# -----------------------------------------------------------------------------
SLIDING_WINDOW_LUA = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
local member = ARGV[4]

local clear_before = now - window
redis.call('ZREMRANGEBYSCORE', key, 0, clear_before)

local current_count = redis.call('ZCARD', key)

if current_count < limit then
    redis.call('ZADD', key, now, member)
    redis.call('EXPIRE', key, math.ceil(window) + 1)
    return {1, limit - current_count - 1, 0}
else
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local reset_seconds = math.ceil(window)
    if #oldest >= 2 then
        local oldest_ts = tonumber(oldest[2])
        reset_seconds = math.max(1, math.ceil((oldest_ts + window) - now))
    end
    return {0, 0, reset_seconds}
end
"""


# -----------------------------------------------------------------------------
# 2. Token Bucket Algorithm (Atomic Lua Script)
# -----------------------------------------------------------------------------
TOKEN_BUCKET_LUA = """
local key = KEYS[1]
local capacity = tonumber(ARGV[1])
local refill_rate = tonumber(ARGV[2])  -- tokens per second
local now = tonumber(ARGV[3])
local window = tonumber(ARGV[4])

local data = redis.call('HMGET', key, 'tokens', 'last_updated')
local tokens = tonumber(data[1])
local last_updated = tonumber(data[2])

if tokens == nil then
    tokens = capacity
    last_updated = now
else
    local elapsed = math.max(0, now - last_updated)
    tokens = math.min(capacity, tokens + (elapsed * refill_rate))
    last_updated = now
end

if tokens >= 1.0 then
    tokens = tokens - 1.0
    redis.call('HMSET', key, 'tokens', tokens, 'last_updated', last_updated)
    redis.call('EXPIRE', key, math.ceil(window) * 2)
    return {1, math.floor(tokens), 0}
else
    local needed = 1.0 - tokens
    local wait_seconds = math.max(1, math.ceil(needed / refill_rate))
    redis.call('HMSET', key, 'tokens', tokens, 'last_updated', last_updated)
    redis.call('EXPIRE', key, math.ceil(window) * 2)
    return {0, 0, wait_seconds}
end
"""


class RateLimiter:
    def __init__(self, redis_client: Optional[redis.Redis] = None):
        self.redis = redis_client or get_redis_client()

    def check_sliding_window(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
    ) -> RateLimitResult:
        """
        Executes an atomic Sliding Window Log check using Redis Sorted Set.
        Accurately enforces rate across exact rolling windows.
        """
        key = f"ratelimit:{identifier}:sliding"
        now = time.time()
        member = f"{now}-{uuid.uuid4().hex[:8]}"

        try:
            res = self.redis.eval(
                SLIDING_WINDOW_LUA,
                1,
                key,
                str(now),
                str(window_seconds),
                str(limit),
                member,
            )
            allowed = bool(res[0])
            remaining = int(res[1])
            reset_seconds = int(res[2]) if not allowed else int(window_seconds - (now % window_seconds))

            return RateLimitResult(
                allowed=allowed,
                limit=limit,
                remaining=remaining,
                reset_seconds=reset_seconds if reset_seconds > 0 else window_seconds,
                retry_after=reset_seconds if not allowed else 0,
            )
        except Exception:
            # Fallback for redis implementations that do not support eval scripts directly
            return self._fallback_sliding_window(key, identifier, limit, window_seconds, now)

    def _fallback_sliding_window(
        self,
        key: str,
        identifier: str,
        limit: int,
        window_seconds: int,
        now: float,
    ) -> RateLimitResult:
        """Python fallback implementation of sliding window."""
        clear_before = now - window_seconds
        pipe = self.redis.pipeline()
        pipe.zremrangebyscore(key, 0, clear_before)
        pipe.zcard(key)
        _, current_count = pipe.execute()

        if current_count < limit:
            member = f"{now}-{uuid.uuid4().hex[:8]}"
            pipe = self.redis.pipeline()
            pipe.zadd(key, {member: now})
            pipe.expire(key, window_seconds + 2)
            pipe.execute()
            return RateLimitResult(
                allowed=True,
                limit=limit,
                remaining=limit - current_count - 1,
                reset_seconds=int(window_seconds),
                retry_after=0,
            )
        else:
            oldest = self.redis.zrange(key, 0, 0, withscores=True)
            reset_sec = window_seconds
            if oldest:
                oldest_ts = oldest[0][1]
                reset_sec = max(1, int((oldest_ts + window_seconds) - now))
            return RateLimitResult(
                allowed=False,
                limit=limit,
                remaining=0,
                reset_seconds=reset_sec,
                retry_after=reset_sec,
            )

    def check_token_bucket(
        self,
        identifier: str,
        capacity: int,
        window_seconds: int = 60,
    ) -> RateLimitResult:
        """
        Executes an atomic Token Bucket check.
        Permits bursts up to `capacity`, with continuous fractional refills.
        """
        key = f"ratelimit:{identifier}:bucket"
        now = time.time()
        refill_rate = capacity / float(window_seconds)

        try:
            res = self.redis.eval(
                TOKEN_BUCKET_LUA,
                1,
                key,
                str(capacity),
                str(refill_rate),
                str(now),
                str(window_seconds),
            )
            allowed = bool(res[0])
            remaining = int(res[1])
            wait_seconds = int(res[2])

            return RateLimitResult(
                allowed=allowed,
                limit=capacity,
                remaining=remaining,
                reset_seconds=wait_seconds if not allowed else int(window_seconds),
                retry_after=wait_seconds if not allowed else 0,
            )
        except Exception:
            return self._fallback_token_bucket(key, capacity, refill_rate, window_seconds, now)

    def _fallback_token_bucket(
        self,
        key: str,
        capacity: int,
        refill_rate: float,
        window_seconds: int,
        now: float,
    ) -> RateLimitResult:
        """Python fallback implementation of token bucket."""
        data = self.redis.hgetall(key)
        tokens = float(data.get("tokens", capacity)) if "tokens" in data else float(capacity)
        last_updated = float(data.get("last_updated", now)) if "last_updated" in data else now

        elapsed = max(0.0, now - last_updated)
        tokens = min(float(capacity), tokens + (elapsed * refill_rate))
        last_updated = now

        if tokens >= 1.0:
            tokens -= 1.0
            self.redis.hset(key, mapping={"tokens": str(tokens), "last_updated": str(last_updated)})
            self.redis.expire(key, window_seconds * 2)
            return RateLimitResult(
                allowed=True,
                limit=capacity,
                remaining=int(tokens),
                reset_seconds=window_seconds,
                retry_after=0,
            )
        else:
            needed = 1.0 - tokens
            wait_sec = max(1, int(needed / refill_rate))
            self.redis.hset(key, mapping={"tokens": str(tokens), "last_updated": str(last_updated)})
            self.redis.expire(key, window_seconds * 2)
            return RateLimitResult(
                allowed=False,
                limit=capacity,
                remaining=0,
                reset_seconds=wait_sec,
                retry_after=wait_sec,
            )

    def check(
        self,
        identifier: str,
        limit: int,
        window_seconds: int = 60,
        algorithm: Optional[str] = None,
    ) -> RateLimitResult:
        """
        Unified dispatch: routes to the requested algorithm (sliding_window or token_bucket).
        """
        algo = algorithm or settings.RATE_LIMIT_ALGORITHM
        if algo == "token_bucket":
            return self.check_token_bucket(identifier, capacity=limit, window_seconds=window_seconds)
        return self.check_sliding_window(identifier, limit=limit, window_seconds=window_seconds)
