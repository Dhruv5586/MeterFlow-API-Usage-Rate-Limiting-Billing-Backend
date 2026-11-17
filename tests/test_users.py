"""
User Endpoints Tests
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

TECHNOVA_USER_ID = "20000000-0000-4000-8000-000000000001"
MISSING_USER_ID = "00000000-0000-0000-0000-000000000000"


@pytest.mark.asyncio
async def test_list_users_paginated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/users?page=1&size=10")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert "page" in data
        assert "size" in data
        assert data["page"] == 1
        assert len(data["items"]) >= 3

        # Check no password_hash leaked
        for u in data["items"]:
            assert "password_hash" not in u
            assert "password" not in u


@pytest.mark.asyncio
async def test_get_user_by_valid_id():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/users/{TECHNOVA_USER_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == TECHNOVA_USER_ID
        assert data["email"] == "admin@technova.io"
        assert data["display_name"] == "TechNova Solutions"
        assert "password_hash" not in data

        # Check nested relationships (api_keys and subscriptions)
        assert "api_keys" in data
        assert len(data["api_keys"]) >= 1
        assert "key_hash" not in data["api_keys"][0]
        assert data["api_keys"][0]["key_prefix"].startswith("mf_live_")

        assert "subscriptions" in data
        assert len(data["subscriptions"]) >= 1
        assert data["subscriptions"][0]["plan_code"] == "enterprise"


@pytest.mark.asyncio
async def test_get_user_missing_404():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/users/{MISSING_USER_ID}")
        assert response.status_code == 404
        data = response.json()
        assert data["error"] == "Not Found"


@pytest.mark.asyncio
async def test_get_user_invalid_uuid_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/users/not-a-valid-uuid")
        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Validation Error"


@pytest.mark.asyncio
async def test_list_users_invalid_pagination_422():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Page cannot be < 1
        response = await client.get("/api/v1/users?page=0")
        assert response.status_code == 422

        # Size cannot be > 100
        response = await client.get("/api/v1/users?size=500")
        assert response.status_code == 422
