"""
Rate Limiter & Quota Enforcement Tests
--------------------------------------
Comprehensive tests for:
1. Redis Sliding Window Log algorithm.
2. Redis Token Bucket algorithm.
3. API Gateway HTTP 429 (Too Many Requests) rejection.
4. Standard Rate Limit Headers:
   - X-RateLimit-Limit
   - X-RateLimit-Remaining
   - X-RateLimit-Reset
   - Retry-After
"""

import time
import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.services.rate_limiter import RateLimiter, RateLimitResult
from app.core.redis import get_redis_client


def test_sliding_window_rate_limiter_enforcement():
    limiter = RateLimiter()
    test_id = f"test_sw_{uuid.uuid4().hex[:8]}"
    limit = 4
    window = 30

    # 1. First 4 requests must be allowed
    for i in range(limit):
        res = limiter.check_sliding_window(test_id, limit=limit, window_seconds=window)
        assert res.allowed is True
        assert res.limit == limit
        assert res.remaining == limit - i - 1
        assert res.reset_seconds > 0

    # 2. 5th request must be rejected (429 condition)
    blocked_res = limiter.check_sliding_window(test_id, limit=limit, window_seconds=window)
    assert blocked_res.allowed is False
    assert blocked_res.remaining == 0
    assert blocked_res.retry_after > 0
    assert "Retry-After" in blocked_res.headers
    assert blocked_res.headers["X-RateLimit-Remaining"] == "0"


def test_token_bucket_burst_and_exhaustion():
    limiter = RateLimiter()
    test_id = f"test_tb_{uuid.uuid4().hex[:8]}"
    capacity = 3
    window = 60

    # 1. Burst through capacity
    for i in range(capacity):
        res = limiter.check_token_bucket(test_id, capacity=capacity, window_seconds=window)
        assert res.allowed is True
        assert res.limit == capacity

    # 2. Immediate next request must be blocked
    blocked_res = limiter.check_token_bucket(test_id, capacity=capacity, window_seconds=window)
    assert blocked_res.allowed is False
    assert blocked_res.remaining == 0
    assert blocked_res.retry_after > 0


@pytest.mark.asyncio
async def test_gateway_rate_limiting_and_429_lifecycle():
    transport = ASGITransport(app=app)
    user_email = f"rl_flow_{uuid.uuid4().hex[:8]}@meterflow.io"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register tenant & create API key
        reg = await client.post("/api/v1/auth/register", json={
            "email": user_email,
            "password": "Password123!",
            "display_name": "Rate Limit Lifecycle Tenant",
        })
        assert reg.status_code == 201
        token = reg.json()["access_token"]

        key_resp = await client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Lifecycle Key"},
        )
        assert key_resp.status_code == 201
        api_key = key_resp.json()["api_key"]
        key_id = key_resp.json()["id"]

        # 2. Normal Request: verify standard headers are injected
        resp = await client.get(
            "/api/v1/gateway/verify",
            headers={"X-API-Key": api_key},
        )
        assert resp.status_code == 200
        headers = resp.headers
        assert "X-RateLimit-Limit" in headers
        assert "X-RateLimit-Remaining" in headers
        assert "X-RateLimit-Reset" in headers
        assert int(headers["X-RateLimit-Limit"]) >= 60

        # 3. Simulate Rate Limit Exhaustion directly in Redis
        redis_client = get_redis_client()
        key_redis_name = f"ratelimit:key:{key_id}:sliding"
        now = time.time()
        pipe = redis_client.pipeline()
        for i in range(70):
            pipe.zadd(key_redis_name, {f"simulated-{i}": now})
        pipe.expire(key_redis_name, 60)
        pipe.execute()

        # 4. Exceeded Request: expect HTTP 429 Too Many Requests
        blocked_resp = await client.get(
            "/api/v1/gateway/verify",
            headers={"X-API-Key": api_key},
        )
        assert blocked_resp.status_code == 429
        assert blocked_resp.headers.get("Retry-After") is not None
        assert blocked_resp.headers.get("X-RateLimit-Remaining") == "0"

        data = blocked_resp.json()
        assert data["error"] == "Too Many Requests"
        assert "Rate limit" in data["message"]
        assert data["remaining"] == 0
        assert data["reset_seconds"] > 0
