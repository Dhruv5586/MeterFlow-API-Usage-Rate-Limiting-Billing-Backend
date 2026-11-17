"""
Usage Endpoints Tests
"""

import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app

TECHNOVA_USER_ID = "20000000-0000-4000-8000-000000000001"


@pytest.mark.asyncio
async def test_get_usage_summary_global():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/usage/summary")
        assert response.status_code == 200
        data = response.json()
        assert "total_requests" in data
        assert "successful_requests" in data
        assert "failed_requests" in data
        assert "average_latency_ms" in data
        assert "total_response_bytes" in data
        assert data["total_requests"] >= 1000
        assert data["successful_requests"] + data["failed_requests"] == data["total_requests"]
        assert data["average_latency_ms"] > 0
        assert data["total_response_bytes"] > 0


@pytest.mark.asyncio
async def test_get_usage_summary_filtered_by_user():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/usage/summary?user_id={TECHNOVA_USER_ID}")
        assert response.status_code == 200
        data = response.json()
        assert data["total_requests"] > 0
        assert data["total_requests"] <= 1000


@pytest.mark.asyncio
async def test_list_usage_events_paginated():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/usage/events?page=1&size=20")
        assert response.status_code == 200
        data = response.json()
        assert "items" in data
        assert len(data["items"]) == 20
        assert data["total"] >= 1000
        assert data["page"] == 1
        assert data["size"] == 20

        # Validate event properties
        event = data["items"][0]
        assert "id" in event
        assert "user_id" in event
        assert "api_key_id" in event
        assert "endpoint" in event
        assert event["endpoint"].startswith("/api/")
        assert "latency_ms" in event
        assert "response_size_bytes" in event


@pytest.mark.asyncio
async def test_list_usage_events_filter_method():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/usage/events?http_method=POST&size=10")
        assert response.status_code == 200
        data = response.json()
        for ev in data["items"]:
            assert ev["http_method"] == "POST"
