"""
Authentication & JWT Tests
--------------------------
Tests for user registration, bcrypt password hashing, JWT issuance,
login authentication, and current profile inspection (/auth/me).
"""

import uuid
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.security import hash_password, verify_password, create_access_token, decode_access_token


def test_security_bcrypt_hashing_and_verification():
    pwd = "SuperSecretPassword123!"
    hashed = hash_password(pwd)
    assert hashed != pwd
    assert hashed.startswith("$2b$")
    assert verify_password(pwd, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False


def test_security_jwt_token_generation_and_decoding():
    user_id = str(uuid.uuid4())
    token, expires_in = create_access_token(subject=user_id, claims={"email": "test@meterflow.io"})
    assert isinstance(token, str)
    assert expires_in > 0

    payload = decode_access_token(token)
    assert payload["sub"] == user_id
    assert payload["email"] == "test@meterflow.io"
    assert payload["iss"] == "MeterFlow"


@pytest.mark.asyncio
async def test_register_new_user_success():
    transport = ASGITransport(app=app)
    unique_email = f"dev_{uuid.uuid4().hex[:8]}@meterflow.io"
    payload = {
        "email": unique_email,
        "password": "StrongPassword987!",
        "display_name": "Apex Innovations",
    }
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/auth/register", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert "access_token" in data
        assert data["token_type"] == "bearer"
        assert data["expires_in"] > 0
        assert "user" in data
        user = data["user"]
        assert user["email"] == unique_email.lower()
        assert user["display_name"] == "Apex Innovations"
        assert "password_hash" not in user
        assert "password" not in user


@pytest.mark.asyncio
async def test_register_duplicate_email_conflict():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # admin@technova.io already exists from demo users
        response = await client.post("/api/v1/auth/register", json={
            "email": "admin@technova.io",
            "password": "Password123!",
            "display_name": "TechNova Clone",
        })
        assert response.status_code == 409
        data = response.json()
        assert data["error"] == "Conflict"
        assert "already exists" in data["message"]


@pytest.mark.asyncio
async def test_register_validation_short_password():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/v1/auth/register", json={
            "email": "test_short@meterflow.io",
            "password": "short",
            "display_name": "Short Pwd",
        })
        assert response.status_code == 422
        data = response.json()
        assert data["error"] == "Validation Error"


@pytest.mark.asyncio
async def test_login_and_me_lifecycle():
    transport = ASGITransport(app=app)
    unique_email = f"user_{uuid.uuid4().hex[:8]}@meterflow.io"
    password = "MySecurePassword123!"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register
        reg_resp = await client.post("/api/v1/auth/register", json={
            "email": unique_email,
            "password": password,
            "display_name": "Lifecycle Tester",
        })
        assert reg_resp.status_code == 201

        # 2. Login with correct credentials
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": unique_email,
            "password": password,
        })
        assert login_resp.status_code == 200
        token_data = login_resp.json()
        access_token = token_data["access_token"]
        assert access_token is not None

        # 3. Access /auth/me with Bearer token
        me_resp = await client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {access_token}"},
        )
        assert me_resp.status_code == 200
        profile = me_resp.json()
        assert profile["email"] == unique_email
        assert profile["display_name"] == "Lifecycle Tester"
        assert "subscriptions" in profile
        assert "api_keys" in profile

        # 4. Login with wrong password
        bad_login = await client.post("/api/v1/auth/login", json={
            "email": unique_email,
            "password": "WrongPassword999!",
        })
        assert bad_login.status_code == 401
        assert "Invalid email or password" in bad_login.json()["message"]


@pytest.mark.asyncio
async def test_me_unauthorized_without_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me")
        assert resp.status_code == 401
        assert resp.json()["error"] == "Unauthorized"


@pytest.mark.asyncio
async def test_me_unauthorized_with_malformed_token():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token.here"})
        assert resp.status_code == 401
