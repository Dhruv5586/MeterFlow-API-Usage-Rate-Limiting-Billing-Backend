"""
API Gateway Header Verification Middleware Tests
------------------------------------------------
Tests for X-API-Key header interception, database hash validation,
revocation enforcement, and gateway authorization.
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_gateway_verification_flow():
    transport = ASGITransport(app=app)
    user_email = f"gw_user_{uuid.uuid4().hex[:8]}@meterflow.io"
    password = "GatewayPassword123!"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register & create key
        reg_resp = await client.post("/api/v1/auth/register", json={
            "email": user_email,
            "password": password,
            "display_name": "Gateway Tenant",
        })
        assert reg_resp.status_code == 201
        token = reg_resp.json()["access_token"]

        create_key_resp = await client.post(
            "/api/v1/api-keys",
            headers={"Authorization": f"Bearer {token}"},
            json={"name": "Gateway Client Key"},
        )
        assert create_key_resp.status_code == 201
        key_data = create_key_resp.json()
        key_id = key_data["id"]
        valid_api_key = key_data["api_key"]
        prefix = key_data["key_prefix"]

        # 2. Test valid X-API-Key on /api/v1/gateway/verify
        gw_resp = await client.get(
            "/api/v1/gateway/verify",
            headers={"X-API-Key": valid_api_key},
        )
        assert gw_resp.status_code == 200
        gw_data = gw_resp.json()
        assert gw_data["status"] == "authorized"
        assert gw_data["key_prefix"] == prefix
        assert gw_data["user_email"] == user_email
        assert gw_data["user_display_name"] == "Gateway Tenant"

        # 3. Test missing X-API-Key header on protected gateway route
        missing_resp = await client.get("/api/v1/gateway/verify")
        assert missing_resp.status_code == 401
        assert "Missing required 'X-API-Key'" in missing_resp.json()["message"]

        # 4. Test invalid/bogus X-API-Key header
        invalid_resp = await client.get(
            "/api/v1/gateway/verify",
            headers={"X-API-Key": "mf_live_completely_bogus_key_xyz"},
        )
        assert invalid_resp.status_code == 401
        assert "Invalid API key" in invalid_resp.json()["message"]

        # 5. Revoke the key
        revoke_resp = await client.delete(
            f"/api/v1/api-keys/{key_id}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert revoke_resp.status_code == 200

        # 6. Test revoked X-API-Key returns 401
        revoked_gw_resp = await client.get(
            "/api/v1/gateway/verify",
            headers={"X-API-Key": valid_api_key},
        )
        assert revoked_gw_resp.status_code == 401
        assert "revoked" in revoked_gw_resp.json()["message"]
