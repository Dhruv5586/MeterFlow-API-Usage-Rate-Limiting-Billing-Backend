"""
Phase 6: Razorpay Webhooks Integration Tests
--------------------------------------------
Comprehensive tests for:
1. Missing or invalid webhook signature rejection (HMAC-SHA256).
2. payment.captured event processing & transactional invoice settlement.
3. Duplicate webhook event idempotency enforcement.
4. payment.failed event handling with error codes.
5. Late or duplicate failure events CANNOT reverse an already captured payment.
6. refund.created and refund.processed event handling.
7. Transaction rollback on unhandled error.
"""

import json
import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from unittest.mock import patch

from app.main import app
from app.core.database import SessionLocal
from app.models.user import User
from app.models.plan import SubscriptionPlan
from app.models.subscription import Subscription
from app.models.invoice import Invoice
from app.models.payment import Payment, PaymentWebhookEvent
from app.services.razorpay_service import RazorpayService


def setup_webhook_test_records(db) -> tuple[User, Invoice, Payment]:
    """Sets up a registered tenant, open invoice, and created payment order."""
    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"webhook_user_{unique}@meterflow.io",
        password_hash="$2b$12$e84W8y.c4dZ4qQWdZ89Zg.n190011800118001180011800118001",
        display_name=f"Webhook User {unique}",
        status="active",
    )
    db.add(user)
    db.flush()

    plan = db.scalars(select(SubscriptionPlan)).first()
    now = datetime.now(timezone.utc)
    sub = Subscription(
        user_id=user.id,
        plan_id=plan.id,
        status="active",
        starts_at=now - timedelta(days=15),
        current_period_start=now - timedelta(days=15),
        current_period_end=now + timedelta(days=15),
    )
    db.add(sub)
    db.flush()

    inv = Invoice(
        user_id=user.id,
        subscription_id=sub.id,
        invoice_number=f"INV-WH-{unique[:4].upper()}",
        status="open",
        currency="USD",
        subtotal=Decimal("29.00"),
        tax=Decimal("0.00"),
        total=Decimal("29.00"),
        issued_at=now,
    )
    db.add(inv)
    db.flush()

    order_id = f"order_{uuid.uuid4().hex[:12]}"
    pay = Payment(
        user_id=user.id,
        invoice_id=inv.id,
        razorpay_order_id=order_id,
        amount=Decimal("29.00"),
        currency="USD",
        status="created",
    )
    db.add(pay)
    db.commit()
    db.refresh(user)
    db.refresh(inv)
    db.refresh(pay)
    return user, inv, pay


@pytest.mark.asyncio
async def test_webhook_invalid_signature():
    """Module 4: Reject webhook requests with missing or forged signature header."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Missing header
        resp1 = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=b'{"event": "payment.captured"}',
            headers={"Content-Type": "application/json"},
        )
        assert resp1.status_code == 400
        assert "signature" in resp1.json()["message"].lower()

        # Forged signature
        resp2 = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=b'{"event": "payment.captured"}',
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": "invalid_forged_sha256_signature",
            },
        )
        assert resp2.status_code == 400
        assert "invalid webhook signature" in resp2.json()["message"].lower()


@pytest.mark.asyncio
async def test_webhook_payment_captured_success():
    """Module 4: Process payment.captured event, capture payment, and settle invoice."""
    db = SessionLocal()
    try:
        user, inv, pay = setup_webhook_test_records(db)
        order_id = pay.razorpay_order_id
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        event_id = f"evt_{uuid.uuid4().hex[:12]}"
    finally:
        db.close()

    rzp_service = RazorpayService()
    payload = {
        "entity": "event",
        "account_id": "acc_test123",
        "event": "payment.captured",
        "id": event_id,
        "contains": ["payment"],
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 2900,
                    "currency": "USD",
                    "status": "captured",
                    "method": "card",
                }
            }
        },
        "created_at": 1700000000,
    }

    raw_body = json.dumps(payload).encode("utf-8")
    sig = rzp_service.generate_test_webhook_signature(raw_body)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=raw_body,
            headers={
                "Content-Type": "application/json",
                "X-Razorpay-Signature": sig,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"

        # Verify DB updates
        db = SessionLocal()
        try:
            updated_pay = db.get(Payment, pay.id)
            assert updated_pay.status == "captured"
            assert updated_pay.razorpay_payment_id == payment_id
            assert updated_pay.captured_at is not None

            updated_inv = db.get(Invoice, inv.id)
            assert updated_inv.status == "paid"
            assert updated_inv.paid_at is not None

            # Verify event idempotency record
            evt = db.scalars(
                select(PaymentWebhookEvent).where(PaymentWebhookEvent.event_id == event_id)
            ).first()
            assert evt is not None
            assert evt.event_type == "payment.captured"
        finally:
            db.close()


@pytest.mark.asyncio
async def test_webhook_duplicate_event_idempotency():
    """Module 4: Re-sending identical webhook event ID must be safely ignored without duplicate execution."""
    db = SessionLocal()
    try:
        user, inv, pay = setup_webhook_test_records(db)
        order_id = pay.razorpay_order_id
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        event_id = f"evt_dup_{uuid.uuid4().hex[:10]}"
    finally:
        db.close()

    rzp_service = RazorpayService()
    payload = {
        "entity": "event",
        "event": "payment.captured",
        "id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": payment_id,
                    "order_id": order_id,
                    "amount": 2900,
                    "currency": "USD",
                    "status": "captured",
                }
            }
        },
        "created_at": 1700000000,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = rzp_service.generate_test_webhook_signature(raw_body)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # First Delivery
        resp1 = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "success"

        # Second Delivery (Duplicate)
        resp2 = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "ignored"
        assert "duplicate" in resp2.json()["message"].lower()


@pytest.mark.asyncio
async def test_webhook_payment_failed():
    """Module 4: Process payment.failed event and record gateway failure reasons."""
    db = SessionLocal()
    try:
        user, inv, pay = setup_webhook_test_records(db)
        order_id = pay.razorpay_order_id
        event_id = f"evt_fail_{uuid.uuid4().hex[:10]}"
    finally:
        db.close()

    rzp_service = RazorpayService()
    payload = {
        "entity": "event",
        "event": "payment.failed",
        "id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid.uuid4().hex[:12]}",
                    "order_id": order_id,
                    "amount": 2900,
                    "currency": "USD",
                    "status": "failed",
                    "error_code": "BAD_REQUEST_ERROR",
                    "error_description": "Payment was declined by issuing bank",
                }
            }
        },
        "created_at": 1700000000,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = rzp_service.generate_test_webhook_signature(raw_body)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert resp.status_code == 200

        db = SessionLocal()
        try:
            updated_pay = db.get(Payment, pay.id)
            assert updated_pay.status == "failed"
            assert updated_pay.error_code == "BAD_REQUEST_ERROR"
            assert "declined" in updated_pay.error_description.lower()
        finally:
            db.close()


@pytest.mark.asyncio
async def test_webhook_late_failure_does_not_reverse_captured_payment():
    """Module 4: Late or out-of-order payment.failed event must NEVER reverse a captured payment."""
    db = SessionLocal()
    try:
        user, inv, pay = setup_webhook_test_records(db)
        # Mark payment as captured first
        pay.status = "captured"
        pay.captured_at = datetime.now(timezone.utc)
        inv.status = "paid"
        inv.paid_at = datetime.now(timezone.utc)
        db.commit()

        order_id = pay.razorpay_order_id
        event_id = f"evt_late_fail_{uuid.uuid4().hex[:10]}"
    finally:
        db.close()

    rzp_service = RazorpayService()
    # Late payment.failed event
    payload = {
        "entity": "event",
        "event": "payment.failed",
        "id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid.uuid4().hex[:12]}",
                    "order_id": order_id,
                    "amount": 2900,
                    "currency": "USD",
                    "status": "failed",
                    "error_code": "LATE_EVENT_ERROR",
                    "error_description": "Delayed failure signal",
                }
            }
        },
        "created_at": 1700000000,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = rzp_service.generate_test_webhook_signature(raw_body)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert resp.status_code == 200

        db = SessionLocal()
        try:
            checked_pay = db.get(Payment, pay.id)
            # MUST REMAIN CAPTURED
            assert checked_pay.status == "captured"

            checked_inv = db.get(Invoice, inv.id)
            # MUST REMAIN PAID
            assert checked_inv.status == "paid"
        finally:
            db.close()


@pytest.mark.asyncio
async def test_webhook_refund_processing():
    """Module 4: Process refund.processed webhook event, update status to refunded and record amount."""
    db = SessionLocal()
    try:
        user, inv, pay = setup_webhook_test_records(db)
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        pay.status = "captured"
        pay.razorpay_payment_id = payment_id
        pay.captured_at = datetime.now(timezone.utc)
        db.commit()

        event_id = f"evt_rf_{uuid.uuid4().hex[:10]}"
        order_id = pay.razorpay_order_id
    finally:
        db.close()

    rzp_service = RazorpayService()
    payload = {
        "entity": "event",
        "event": "refund.processed",
        "id": event_id,
        "payload": {
            "refund": {
                "entity": {
                    "id": f"rfnd_{uuid.uuid4().hex[:12]}",
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "amount": 2900,  # $29.00
                    "currency": "USD",
                    "status": "processed",
                }
            }
        },
        "created_at": 1700000000,
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = rzp_service.generate_test_webhook_signature(raw_body)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post(
            "/api/v1/payments/webhooks/razorpay",
            content=raw_body,
            headers={"Content-Type": "application/json", "X-Razorpay-Signature": sig},
        )
        assert resp.status_code == 200

        db = SessionLocal()
        try:
            refunded_pay = db.get(Payment, pay.id)
            assert refunded_pay.status == "refunded"
            assert refunded_pay.amount_refunded == Decimal("29.00")
            assert refunded_pay.refunded_at is not None
        finally:
            db.close()


@pytest.mark.asyncio
async def test_webhook_transaction_rollback_on_error():
    """Module 4: Ensure database rollback occurs if an unhandled error arises during webhook handling."""
    db = SessionLocal()
    try:
        user, inv, pay = setup_webhook_test_records(db)
        order_id = pay.razorpay_order_id
        event_id = f"evt_err_{uuid.uuid4().hex[:10]}"
        pay_id = pay.id
    finally:
        db.close()

    rzp_service = RazorpayService()
    payload = {
        "entity": "event",
        "event": "payment.captured",
        "id": event_id,
        "payload": {
            "payment": {
                "entity": {
                    "id": f"pay_{uuid.uuid4().hex[:12]}",
                    "order_id": order_id,
                    "amount": 2900,
                    "currency": "USD",
                }
            }
        },
    }
    raw_body = json.dumps(payload).encode("utf-8")
    sig = rzp_service.generate_test_webhook_signature(raw_body)

    # Test transactional rollback on unhandled error
    test_db = SessionLocal()
    try:
        from app.services.payment_service import PaymentService
        service = PaymentService(test_db)
        with patch.object(service.payment_repo, "save_webhook_event", side_effect=RuntimeError("Simulated DB Crash")):
            with pytest.raises(RuntimeError, match="Simulated DB Crash"):
                service.process_webhook(raw_body=raw_body, signature_header=sig)

        # Verify rollback: payment must remain 'created'
        rolled_back_pay = test_db.get(Payment, pay_id)
        assert rolled_back_pay.status == "created"
        assert rolled_back_pay.captured_at is None
    finally:
        test_db.close()
