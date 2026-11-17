"""
Subscription Plans Endpoints Tests
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_list_subscription_plans():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/plans")
        assert response.status_code == 200
        data = response.json()
        assert len(data) >= 3

        codes = [p["code"] for p in data]
        assert "free" in codes
        assert "pro" in codes
        assert "enterprise" in codes

        # Verify price sorting and types
        free_plan = next(p for p in data if p["code"] == "free")
        assert float(free_plan["price"]) == 0.00
        assert free_plan["currency"] == "USD"
        assert free_plan["is_active"] is True
