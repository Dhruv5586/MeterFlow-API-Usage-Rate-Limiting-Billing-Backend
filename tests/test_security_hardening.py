"""
Security Hardening & Rate Limiting Tests (Step 18)
--------------------------------------------------
Validates:
1. SecurityHeadersMiddleware (X-Content-Type-Options, X-Frame-Options, Referrer-Policy, CSP, HSTS).
2. Client IP Rate Limiting on POST /api/v1/auth/login and POST /api/v1/auth/register.
3. Prevention of IP-spoofing via untrusted X-Forwarded-For headers.
4. Correct 429 Too Many Requests and Retry-After response headers.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport

from app.main import app
from app.core.config import settings
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_security_headers_present_on_all_responses():
    """Verifies standard OWASP security response headers on normal endpoints."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health")
        assert response.status_code == 200

        headers = response.headers
        assert headers.get("X-Content-Type-Options") == "nosniff"
        assert headers.get("X-Frame-Options") == "DENY"
        assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
        assert headers.get("Content-Security-Policy") == "default-src 'none'; frame-ancestors 'none'"
        # HSTS should NOT be present on plain HTTP requests
        assert "Strict-Transport-Security" not in headers


@pytest.mark.asyncio
async def test_hsts_header_present_when_https_enabled():
    """Verifies Strict-Transport-Security header is injected when request is over HTTPS."""
    transport = ASGITransport(app=app)
    # Simulate HTTPS request via x-forwarded-proto
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/health", headers={"x-forwarded-proto": "https"})
        assert response.status_code == 200
        assert "Strict-Transport-Security" in response.headers
        assert "max-age=31536000" in response.headers["Strict-Transport-Security"]
        assert "includeSubDomains" in response.headers["Strict-Transport-Security"]


@pytest.mark.asyncio
async def test_auth_login_ip_rate_limiting():
    """
    Verifies that POST /api/v1/auth/login allows up to 10 requests per minute
    per client IP, and throttles the 11th with HTTP 429.
    """
    client_ip = f"192.0.2.{uuid.uuid4().int % 250 + 1}"
    transport = ASGITransport(app=app, client=(client_ip, 50000))

    # Use RateLimiter directly to reset test bucket
    limiter = RateLimiter()
    try:
        limiter.redis.delete(f"ratelimit:auth:ip:{client_ip}:sliding")
    except Exception:
        pass

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Send 10 login attempts (limit = 10)
        for i in range(10):
            res = await client.post(
                "/api/v1/auth/login",
                json={"email": "nonexistent@meterflow.io", "password": "WrongPassword123!"},
            )
            # Should be 401 Unauthorized, not 429
            assert res.status_code == 401, f"Attempt {i+1} failed with {res.status_code}"
            assert "X-RateLimit-Limit" in res.headers
            assert res.headers["X-RateLimit-Limit"] == "10"
            assert int(res.headers["X-RateLimit-Remaining"]) == 10 - i - 1

        # 11th request must be throttled with HTTP 429
        res_throttled = await client.post(
            "/api/v1/auth/login",
            json={"email": "nonexistent@meterflow.io", "password": "WrongPassword123!"},
        )
        assert res_throttled.status_code == 429
        assert "Retry-After" in res_throttled.headers
        assert int(res_throttled.headers["Retry-After"]) > 0
        data = res_throttled.json()
        assert data["error"] == "Too Many Requests"
        assert "Rate limit of 10 requests per minute exceeded" in data["message"]


@pytest.mark.asyncio
async def test_auth_register_ip_rate_limiting():
    """
    Verifies that POST /api/v1/auth/register enforces the 10 req/min rate limit per IP.
    """
    client_ip = f"198.51.100.{uuid.uuid4().int % 250 + 1}"
    transport = ASGITransport(app=app, client=(client_ip, 50000))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Exhaust 10 requests
        for i in range(10):
            res = await client.post(
                "/api/v1/auth/register",
                json={"email": "invalid-email-format", "password": "short"},
            )
            assert res.status_code == 422  # validation error, but counted against rate limit

        # 11th request must be throttled
        res_throttled = await client.post(
            "/api/v1/auth/register",
            json={"email": "valid@meterflow.io", "password": "Password123!"},
        )
        assert res_throttled.status_code == 429
        assert "Retry-After" in res_throttled.headers


@pytest.mark.asyncio
async def test_ip_spoofing_prevention_with_untrusted_forwarded_for():
    """
    Verifies that arbitrary clients cannot bypass rate limiting by spoofing
    X-Forwarded-For headers when coming from an untrusted peer.
    """
    actual_peer_ip = f"203.0.113.{uuid.uuid4().int % 250 + 1}"
    transport = ASGITransport(app=app, client=(actual_peer_ip, 50000))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Exhaust 10 requests from this peer, sending fake X-Forwarded-For on each
        for i in range(10):
            fake_ip = f"10.0.0.{i+1}"
            res = await client.post(
                "/api/v1/auth/login",
                headers={"X-Forwarded-For": fake_ip},
                json={"email": "hacker@evil.com", "password": "WrongPassword!"},
            )
            assert res.status_code == 401

        # 11th request with yet another fake IP must still be blocked because actual_peer_ip is untrusted
        res_throttled = await client.post(
            "/api/v1/auth/login",
            headers={"X-Forwarded-For": "10.0.0.99"},
            json={"email": "hacker@evil.com", "password": "WrongPassword!"},
        )
        assert res_throttled.status_code == 429
        assert "Retry-After" in res_throttled.headers


@pytest.mark.asyncio
async def test_non_auth_endpoints_not_throttled_by_auth_limiter():
    """Verifies that general API endpoints (like /plans) are not throttled by the auth IP rate limiter."""
    client_ip = f"192.0.2.{uuid.uuid4().int % 250 + 1}"
    transport = ASGITransport(app=app, client=(client_ip, 50000))

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Making 15 requests to /plans should NOT trigger auth rate limiter
        for _ in range(15):
            res = await client.get("/api/v1/plans")
            assert res.status_code == 200
