"""
API Key Management & Lifecycle Tests
------------------------------------
Tests for generating high-entropy API keys, listing tenant keys,
inspecting active status, and revoking API keys.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_api_key_creation_listing_and_revocation():
    transport = ASGITransport(app=app)
    user_email = f"key_tester_{uuid.uuid4().hex[:8]}@meterflow.io"
    password = "KeyPassword123!"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register & get JWT
        reg_resp = await client.post("/api/v1/auth/register", json={
            "email": user_email,
            "password": password,
            "display_name": "API Key Tester",
        })
        assert reg_resp.status_code == 201
        token = reg_resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {token}"}

        # 2. List keys initially (should be empty for new user)
        list_resp = await client.get("/api/v1/api-keys", headers=auth_headers)
        assert list_resp.status_code == 200
        assert list_resp.json() == []

        # 3. Create a new API key
        create_resp = await client.post(
            "/api/v1/api-keys",
            headers=auth_headers,
            json={"name": "Production Microservice Key", "expires_in_days": 90},
        )
        assert create_resp.status_code == 201
        created_data = create_resp.json()
        key_id = created_data["id"]
        full_key = created_data["api_key"]
        prefix = created_data["key_prefix"]

        assert full_key.startswith("mf_live_")
        assert prefix == full_key[:16]
        assert created_data["expires_at"] is not None
        assert "Store this API key safely" in created_data["message"]

        # 4. List keys again (now contains 1 active key)
        list_resp2 = await client.get("/api/v1/api-keys", headers=auth_headers)
        assert list_resp2.status_code == 200
        keys_list = list_resp2.json()
        assert len(keys_list) == 1
        key_summary = keys_list[0]
        assert key_summary["id"] == key_id
        assert key_summary["key_prefix"] == prefix
        assert key_summary["is_active"] is True
        assert key_summary["revoked_at"] is None
        # Secret plaintext and hash must NEVER be leaked in list view
        assert "api_key" not in key_summary
        assert "key_hash" not in key_summary

        # 5. Revoke the key
        revoke_resp = await client.delete(f"/api/v1/api-keys/{key_id}", headers=auth_headers)
        assert revoke_resp.status_code == 200
        revoke_data = revoke_resp.json()
        assert revoke_data["id"] == key_id
        assert revoke_data["revoked_at"] is not None
        assert "successfully revoked" in revoke_data["message"]

        # 6. Verify key is marked inactive
        list_resp3 = await client.get("/api/v1/api-keys", headers=auth_headers)
        assert list_resp3.status_code == 200
        revoked_summary = list_resp3.json()[0]
        assert revoked_summary["is_active"] is False
        assert revoked_summary["revoked_at"] is not None


@pytest.mark.asyncio
async def test_revoke_nonexistent_key_returns_404():
    transport = ASGITransport(app=app)
    user_email = f"user_{uuid.uuid4().hex[:8]}@meterflow.io"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg_resp = await client.post("/api/v1/auth/register", json={
            "email": user_email,
            "password": "Password123!",
            "display_name": "Tester 404",
        })
        token = reg_resp.json()["access_token"]
        random_uuid = str(uuid.uuid4())

        resp = await client.delete(
            f"/api/v1/api-keys/{random_uuid}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 404
        assert resp.json()["error"] == "Not Found"


@pytest.mark.asyncio
async def test_api_keys_requires_authentication():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # GET without auth
        resp_get = await client.get("/api/v1/api-keys")
        assert resp_get.status_code == 401

        # POST without auth
        resp_post = await client.post("/api/v1/api-keys", json={"name": "No Auth"})
        assert resp_post.status_code == 401
