"""
MeterFlow Full Customer Lifecycle End-to-End Integration Suite (Step 18)
------------------------------------------------------------------------
Validates the entire, uninterrupted 13-stage customer journey:
1. Register a new customer.
2. Login and obtain JWT access token.
3. Subscribe to a tier plan (Pro tier with quota & overages).
4. Generate a secure, cryptographically hashed API key.
5. Send authenticated traffic through the API Gateway (X-API-Key).
6. Verify usage tracking and event ingestion.
7. Verify quota warning (>=80%) and rate limiting headers.
8. Run daily aggregation rollup (usage_events -> usage_daily).
9. Generate a monthly invoice with base price and tiered overage charges.
10. Create a mocked Razorpay payment order in minor units.
11. Verify cryptographic payment signature.
12. Process a captured-payment webhook with idempotency check.
13. Verify final invoice settlement and payment audit history.
"""

import hmac
import hashlib
import json
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta, date
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.config import settings
from app.core.database import SessionLocal
from app.models.user import User
from app.models.plan import SubscriptionPlan
from app.models.subscription import Subscription
from app.models.api_key import APIKey
from app.models.usage_event import UsageEvent
from app.models.usage_daily import UsageDaily
from app.models.invoice import Invoice, InvoiceItem
from app.models.payment import Payment
from app.services.rate_limiter import RateLimiter


@pytest.mark.asyncio
async def test_full_customer_lifecycle_e2e(db_session_rollback):
    transport = ASGITransport(app=app)
    unique_suffix = uuid.uuid4().hex[:8]
    customer_email = f"e2e_enterprise_{unique_suffix}@meterflow.io"
    customer_password = "SuperSecurePassword123!"
    display_name = f"E2E Enterprise Corp {unique_suffix}"

    db = db_session_rollback

    async with AsyncClient(transport=transport, base_url="http://test") as client:

        # ---------------------------------------------------------------------
        # Stage 1: Register a new customer
        # ---------------------------------------------------------------------
        reg_payload = {
            "email": customer_email,
            "password": customer_password,
            "display_name": display_name,
        }
        reg_resp = await client.post("/api/v1/auth/register", json=reg_payload)
        assert reg_resp.status_code == 201, f"Registration failed: {reg_resp.text}"
        reg_data = reg_resp.json()
        assert "access_token" in reg_data
        user_id = uuid.UUID(reg_data["user"]["id"])
        assert reg_data["user"]["email"] == customer_email.lower()

        # ---------------------------------------------------------------------
        # Stage 2: Login and obtain JWT access token
        # ---------------------------------------------------------------------
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": customer_email,
            "password": customer_password,
        })
        assert login_resp.status_code == 200, f"Login failed: {login_resp.text}"
        jwt_token = login_resp.json()["access_token"]
        auth_headers = {"Authorization": f"Bearer {jwt_token}"}

        # Inspect current user profile (/auth/me)
        me_resp = await client.get("/api/v1/auth/me", headers=auth_headers)
        assert me_resp.status_code == 200
        me_data = me_resp.json()
        assert me_data["id"] == str(user_id)
        assert me_data["status"] == "active"

        # ---------------------------------------------------------------------
        # Stage 3: Subscribe to a plan (Pro Tier with Quota & Overage Pricing)
        # ---------------------------------------------------------------------
        plans_resp = await client.get("/api/v1/plans")
        assert plans_resp.status_code == 200
        plans_list = plans_resp.json()
        pro_plan_info = next((p for p in plans_list if p["code"] == "pro"), None)
        assert pro_plan_info is not None, "Pro plan not found in plan catalog"
        pro_plan_id = uuid.UUID(pro_plan_info["id"])

        # Upgrade customer subscription to Pro in test database
        now = datetime.now(timezone.utc)
        start_period = now - timedelta(days=20)
        end_period = now + timedelta(days=10)

        sub = db.scalars(
            select(Subscription).where(Subscription.user_id == user_id)
        ).first()
        if sub:
            sub.plan_id = pro_plan_id
            sub.current_period_start = start_period
            sub.current_period_end = end_period
        else:
            sub = Subscription(
                user_id=user_id,
                plan_id=pro_plan_id,
                status="active",
                starts_at=start_period,
                current_period_start=start_period,
                current_period_end=end_period,
            )
            db.add(sub)
        db.commit()
        db.refresh(sub)
        subscription_id = sub.id

        # ---------------------------------------------------------------------
        # Stage 4: Generate an API Key
        # ---------------------------------------------------------------------
        key_req = {
            "name": f"Production Key {unique_suffix}",
            "expires_in_days": 90,
        }
        key_resp = await client.post("/api/v1/api-keys", json=key_req, headers=auth_headers)
        assert key_resp.status_code == 201, f"Key generation failed: {key_resp.text}"
        key_data = key_resp.json()
        raw_api_key = key_data["api_key"]
        api_key_id = uuid.UUID(key_data["id"])
        assert raw_api_key.startswith("mf_live_")

        # ---------------------------------------------------------------------
        # Stage 5: Send authenticated traffic through API Gateway
        # ---------------------------------------------------------------------
        gateway_headers = {"X-API-Key": raw_api_key}
        verify_resp = await client.get("/api/v1/gateway/verify", headers=gateway_headers)
        assert verify_resp.status_code == 200, f"Gateway verify failed: {verify_resp.text}"
        verify_data = verify_resp.json()
        assert verify_data["status"] == "authorized"
        assert verify_data["key_id"] == str(api_key_id)
        assert verify_data["user_id"] == str(user_id)

        echo_resp = await client.get("/api/v1/gateway/echo", headers=gateway_headers)
        assert echo_resp.status_code == 200
        assert echo_resp.json()["service"] == "downstream-echo"

        # ---------------------------------------------------------------------
        # Stage 6: Verify usage tracking
        # ---------------------------------------------------------------------
        # Seed 105,000 recorded access requests for the customer to exceed Pro quota (100,000)
        # by 5,000 units to test overage charges.
        event_date = now.date() - timedelta(days=2)
        prior_date = now.date() - timedelta(days=3)
        event_timestamp = datetime.combine(event_date, datetime.min.time(), tzinfo=timezone.utc)

        # 1. Insert a raw usage event on event_date (to be aggregated by Stage 8 rollup)
        test_event = UsageEvent(
            user_id=user_id,
            subscription_id=subscription_id,
            api_key_id=api_key_id,
            endpoint="/api/v1/gateway/verify",
            http_method="GET",
            status_code=200,
            latency_ms=42,
            response_size_bytes=512,
            source_record_key=f"e2e_rec_{unique_suffix}_1",
            created_at=event_timestamp,
        )
        db.add(test_event)

        # 2. Insert pre-aggregated daily usage for prior_date with 104,999 requests
        # After Stage 8 rollup of event_date (1 request), total recorded = 105,000 requests!
        daily_usage = UsageDaily(
            user_id=user_id,
            usage_date=prior_date,
            subscription_id=subscription_id,
            api_key_id=api_key_id,
            endpoint="/api/v1/gateway/verify",
            http_method="GET",
            request_count=104999,
            successful_request_count=104949,
            error_request_count=50,
            latency_sum_ms=4462458,
            response_bytes=53759488,
        )
        db.add(daily_usage)
        db.commit()

        # Query usage summary endpoint
        usage_resp = await client.get(f"/api/v1/usage/summary?user_id={user_id}")
        assert usage_resp.status_code == 200
        usage_summary = usage_resp.json()
        assert usage_summary["total_requests"] >= 1

        # ---------------------------------------------------------------------
        # Stage 7: Verify quota warning and rate limiting headers
        # ---------------------------------------------------------------------
        # Set Redis monthly counter to 85,000 (>=80% soft warning threshold for 100k Pro plan)
        limiter = RateLimiter()
        month_key = f"quota:{subscription_id}:{now.strftime('%Y-%m')}"
        try:
            limiter.redis.set(month_key, 85000)
        except Exception:
            pass

        quota_probe = await client.get("/api/v1/gateway/verify", headers=gateway_headers)
        assert quota_probe.status_code == 200
        # Check standard rate limit and warning headers
        assert "X-RateLimit-Limit" in quota_probe.headers
        assert "X-RateLimit-Remaining" in quota_probe.headers
        assert "X-Quota-Warning" in quota_probe.headers
        assert ">=80%" in quota_probe.headers["X-Quota-Warning"]

        # ---------------------------------------------------------------------
        # Stage 8: Run daily aggregation rollup
        # ---------------------------------------------------------------------
        rollup_resp = await client.post(
            f"/api/v1/billing/rollup?target_date={event_date.isoformat()}",
            headers=auth_headers,
        )
        assert rollup_resp.status_code == 200, f"Rollup failed: {rollup_resp.text}"
        rollup_data = rollup_resp.json()
        assert rollup_data["status"] == "success"

        # ---------------------------------------------------------------------
        # Stage 9: Generate a monthly invoice with overage charges
        # ---------------------------------------------------------------------
        # Preview billing accrual first
        preview_resp = await client.get("/api/v1/billing/preview", headers=auth_headers)
        assert preview_resp.status_code == 200
        preview = preview_resp.json()
        assert preview["plan_code"] == "pro"
        assert Decimal(str(preview["base_plan_price"])) == Decimal("29.00")
        assert preview["total_requests_recorded"] >= 105000
        assert preview["overage_requests"] >= 5000
        # 5,000 overages @ $0.0100 / 1k = $0.05
        assert Decimal(str(preview["overage_amount"])) == Decimal("0.05")
        expected_total = Decimal("29.05")
        assert Decimal(str(preview["estimated_total"])) == expected_total

        # Generate finalized invoice
        gen_resp = await client.post("/api/v1/billing/invoices/generate", headers=auth_headers)
        assert gen_resp.status_code == 201, f"Invoice generation failed: {gen_resp.text}"
        invoice_data = gen_resp.json()
        invoice_id = uuid.UUID(invoice_data["id"])
        assert invoice_data["status"] == "open"
        assert Decimal(str(invoice_data["total"])) == expected_total
        assert len(invoice_data["items"]) >= 2  # Base Plan + Overage Fees

        # ---------------------------------------------------------------------
        # Stage 10: Create a mocked Razorpay payment order
        # ---------------------------------------------------------------------
        order_resp = await client.post(
            "/api/v1/payments/orders",
            json={"invoice_id": str(invoice_id)},
            headers=auth_headers,
        )
        assert order_resp.status_code == 201, f"Payment order creation failed: {order_resp.text}"
        order_data = order_resp.json()
        razorpay_order_id = order_data["order_id"]
        # $29.05 = 2905 cents in minor units
        assert order_data["amount"] == 2905
        assert order_data["currency"] == "USD"
        assert razorpay_order_id.startswith("order_")

        # ---------------------------------------------------------------------
        # Stage 11: Verify payment signature
        # ---------------------------------------------------------------------
        mock_payment_id = f"pay_{uuid.uuid4().hex[:14]}"
        message = f"{razorpay_order_id}|{mock_payment_id}".encode("utf-8")
        valid_signature = hmac.new(
            settings.RAZORPAY_KEY_SECRET.encode("utf-8"),
            message,
            hashlib.sha256,
        ).hexdigest()

        verify_payment_resp = await client.post(
            "/api/v1/payments/verify",
            json={
                "razorpay_order_id": razorpay_order_id,
                "razorpay_payment_id": mock_payment_id,
                "razorpay_signature": valid_signature,
            },
            headers=auth_headers,
        )
        assert verify_payment_resp.status_code == 200, f"Payment verification failed: {verify_payment_resp.text}"
        payment_record = verify_payment_resp.json()
        assert payment_record["status"] == "captured"
        assert Decimal(str(payment_record["amount"])) == expected_total

        # ---------------------------------------------------------------------
        # Stage 12: Process a captured-payment webhook with idempotency check
        # ---------------------------------------------------------------------
        webhook_event_id = f"evt_e2e_{uuid.uuid4().hex[:12]}"
        webhook_payload_dict = {
            "entity": "event",
            "account_id": "acc_mock123",
            "event": "payment.captured",
            "contains": ["payment"],
            "payload": {
                "payment": {
                    "entity": {
                        "id": mock_payment_id,
                        "order_id": razorpay_order_id,
                        "amount": 2905,
                        "currency": "USD",
                        "status": "captured",
                        "method": "card",
                        "captured": True,
                    }
                }
            },
            "created_at": int(now.timestamp()),
        }
        webhook_raw_bytes = json.dumps(webhook_payload_dict).encode("utf-8")
        webhook_signature = hmac.new(
            settings.RAZORPAY_WEBHOOK_SECRET.encode("utf-8"),
            webhook_raw_bytes,
            hashlib.sha256,
        ).hexdigest()

        webhook_headers = {
            "Content-Type": "application/json",
            "X-Razorpay-Signature": webhook_signature,
        }

        # 1st Webhook delivery -> Processed successfully
        wh_resp1 = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=webhook_raw_bytes,
            headers=webhook_headers,
        )
        assert wh_resp1.status_code == 200
        wh_data1 = wh_resp1.json()
        assert wh_data1["status"] == "success"

        # 2nd Webhook delivery (identical payload) -> Enforce idempotency (duplicate ignored safely)
        wh_resp2 = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=webhook_raw_bytes,
            headers=webhook_headers,
        )
        assert wh_resp2.status_code == 200
        wh_data2 = wh_resp2.json()
        assert wh_data2["status"] == "ignored"
        assert "duplicate" in wh_data2["message"].lower()

        # ---------------------------------------------------------------------
        # Stage 13: Verify invoice settlement & audit payment history
        # ---------------------------------------------------------------------
        final_inv_resp = await client.get(f"/api/v1/billing/invoices/{invoice_id}", headers=auth_headers)
        assert final_inv_resp.status_code == 200
        final_invoice = final_inv_resp.json()
        assert final_invoice["status"] == "paid"
        assert final_invoice["paid_at"] is not None

        # Verify payment history reflects captured settlement
        payments_history_resp = await client.get(
            f"/api/v1/invoices/{invoice_id}/payments",
            headers=auth_headers,
        )
        assert payments_history_resp.status_code == 200
        history = payments_history_resp.json()
        assert len(history) >= 1
        assert history[0]["status"] == "captured"
        assert history[0]["razorpay_order_id"] == razorpay_order_id
        assert history[0]["razorpay_payment_id"] == mock_payment_id
