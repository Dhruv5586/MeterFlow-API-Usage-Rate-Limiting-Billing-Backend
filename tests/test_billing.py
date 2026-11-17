"""
Phase 5: Daily Aggregations & Billing Engine Tests
-------------------------------------------------
Comprehensive tests for:
1. Daily usage rollup worker (usage_events -> usage_daily aggregation & idempotency).
2. Real-time billing previews.
3. Itemized invoice generation with base fees and tiered overage fees.
4. Invoice listing, line item retrieval, and payment settlement.
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date
import pytest
from httpx import AsyncClient, ASGITransport
from app.main import app
from app.core.database import SessionLocal
from app.models.usage_daily import UsageDaily
from app.models.invoice import Invoice, InvoiceItem
from app.services.aggregation_service import AggregationService
from app.services.billing_service import BillingService


def test_daily_aggregation_worker_idempotency():
    db = SessionLocal()
    try:
        service = AggregationService(db)
        
        # 1. Run aggregation across all dates
        stats1 = service.rollup_daily_usage()
        assert stats1["rows_affected"] >= 0
        assert stats1["total_requests_aggregated"] >= 1000

        # 2. Re-run aggregation (must be strictly idempotent without duplicate errors)
        stats2 = service.rollup_daily_usage()
        assert stats2["total_requests_aggregated"] == stats1["total_requests_aggregated"]
        assert stats2["days_covered"] == stats1["days_covered"]
    finally:
        db.close()


@pytest.mark.asyncio
async def test_billing_preview_endpoint():
    transport = ASGITransport(app=app)
    user_email = f"billing_preview_{uuid.uuid4().hex[:8]}@meterflow.io"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user with default Free plan
        reg = await client.post("/api/v1/auth/register", json={
            "email": user_email,
            "password": "BillingPassword123!",
            "display_name": "Preview Tenant",
        })
        assert reg.status_code == 201
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # Preview billing
        resp = await client.get("/api/v1/billing/preview", headers=headers)
        assert resp.status_code == 200
        data = resp.json()

        assert data["plan_code"] == "free"
        assert Decimal(str(data["base_plan_price"])) == Decimal("0.00")
        assert data["requests_included"] == 10_000
        assert data["currency"] == "USD"
        assert Decimal(str(data["estimated_total"])) >= Decimal("0.00")


@pytest.mark.asyncio
async def test_invoice_generation_listing_and_payment_lifecycle():
    transport = ASGITransport(app=app)
    user_email = f"invoice_user_{uuid.uuid4().hex[:8]}@meterflow.io"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # 1. Register
        reg = await client.post("/api/v1/auth/register", json={
            "email": user_email,
            "password": "Password123!",
            "display_name": "Invoiced Tenant",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        # 2. Generate Invoice
        gen_resp = await client.post("/api/v1/billing/invoices/generate", headers=headers, json={})
        assert gen_resp.status_code == 201
        inv_data = gen_resp.json()
        invoice_id = inv_data["id"]
        inv_num = inv_data["invoice_number"]

        assert inv_num.startswith("INV-")
        assert "items" in inv_data
        assert len(inv_data["items"]) >= 1
        base_item = inv_data["items"][0]
        assert "Base Subscription" in base_item["description"]

        # 3. List Invoices
        list_resp = await client.get("/api/v1/billing/invoices", headers=headers)
        assert list_resp.status_code == 200
        invoices = list_resp.json()
        assert any(i["id"] == invoice_id for i in invoices)

        # 4. Get Invoice by ID
        get_resp = await client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=headers)
        assert get_resp.status_code == 200
        detail = get_resp.json()
        assert detail["id"] == invoice_id
        assert detail["invoice_number"] == inv_num
        assert len(detail["items"]) >= 1

        # 5. Settle / Pay Invoice
        pay_resp = await client.post(f"/api/v1/billing/invoices/{invoice_id}/pay", headers=headers)
        assert pay_resp.status_code == 200
        paid_data = pay_resp.json()
        assert paid_data["status"] == "paid"
        assert paid_data["paid_at"] is not None


@pytest.mark.asyncio
async def test_trigger_daily_rollup_endpoint():
    transport = ASGITransport(app=app)
    user_email = f"rollup_user_{uuid.uuid4().hex[:8]}@meterflow.io"

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": user_email,
            "password": "Password123!",
            "display_name": "Rollup Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}

        resp = await client.post("/api/v1/billing/rollup", headers=headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert "statistics" in data
        assert data["statistics"]["total_requests_aggregated"] >= 1000
