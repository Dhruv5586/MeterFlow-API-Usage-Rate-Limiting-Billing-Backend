"""
Phase 6: Payment Orders, Signatures, and Verification Tests
-----------------------------------------------------------
Comprehensive tests for:
1. Payment order creation (minor units conversion, Razorpay order ref).
2. Invoice ownership verification (rejection of cross-tenant attempts).
3. Rejection of already-paid invoices.
4. Cryptographic HMAC-SHA256 signature verification (invalid signature rejection).
5. Valid payment signature verification and transactional invoice settlement.
6. Amount mismatch rejection.
7. Currency mismatch rejection.
8. Duplicate payment verification idempotency.
9. Unauthorized payment access protection.
10. Payment history endpoints (/payments/{id} and /invoices/{id}/payments).
"""

import uuid
from decimal import Decimal
from datetime import datetime, timezone, timedelta
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select

from app.main import app
from app.core.database import SessionLocal
from app.models.user import User
from app.models.plan import SubscriptionPlan
from app.models.subscription import Subscription
from app.models.invoice import Invoice, InvoiceItem
from app.models.payment import Payment
from app.services.razorpay_service import RazorpayService


def create_test_tenant(db, prefix="pay_tenant") -> tuple[User, Subscription, Invoice]:
    """Helper to provision a realistic tenant with an open payable invoice."""
    # 1. User
    unique = uuid.uuid4().hex[:8]
    user = User(
        email=f"{prefix}_{unique}@meterflow.io",
        password_hash="$2b$12$e84W8y.c4dZ4qQWdZ89Zg.n190011800118001180011800118001",
        display_name=f"Tenant {unique}",
        status="active",
    )
    db.add(user)
    db.flush()

    # 2. Plan
    plan = db.scalars(select(SubscriptionPlan).where(SubscriptionPlan.code == "pro")).first()
    if not plan:
        plan = SubscriptionPlan(
            code="pro",
            name="Pro Tier",
            price=Decimal("29.00"),
            currency="USD",
            billing_interval="month",
        )
        db.add(plan)
        db.flush()

    # 3. Subscription
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

    # 4. Open Invoice
    inv = Invoice(
        user_id=user.id,
        subscription_id=sub.id,
        invoice_number=f"INV-{now.strftime('%Y%m')}-{uuid.uuid4().hex[:4].upper()}",
        status="open",
        currency="USD",
        subtotal=Decimal("29.00"),
        tax=Decimal("0.00"),
        total=Decimal("29.00"),
        issued_at=now,
    )
    db.add(inv)
    db.flush()

    item = InvoiceItem(
        invoice_id=inv.id,
        description="Pro Tier Monthly Base Subscription",
        quantity=Decimal("1.0000"),
        unit_price=Decimal("29.0000"),
        line_amount=Decimal("29.00"),
    )
    db.add(item)
    db.commit()
    db.refresh(user)
    db.refresh(inv)
    return user, sub, inv


@pytest.mark.asyncio
async def test_payment_order_creation():
    """Module 2: Create a Razorpay test order for a payable invoice."""
    db = SessionLocal()
    try:
        user, sub, inv = create_test_tenant(db, "order_create")
    finally:
        db.close()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Login to obtain JWT
        login_resp = await client.post("/api/v1/auth/login", json={
            "email": user.email,
            "password": "Password123!",  # Note: our helper creates a dummy hash, login endpoint expects valid verification
        })
        # If hash is dummy, generate token directly or register via API
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"order_api_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "StrongPassword123!",
            "display_name": "Order Client",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(reg.json()["user"]["id"])

        # Create an open invoice for this registered user
        db = SessionLocal()
        try:
            sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
            inv = Invoice(
                user_id=user_id,
                subscription_id=sub.id,
                invoice_number=f"INV-TEST-{uuid.uuid4().hex[:4].upper()}",
                status="open",
                currency="USD",
                subtotal=Decimal("49.00"),
                tax=Decimal("0.00"),
                total=Decimal("49.00"),
                issued_at=datetime.now(timezone.utc),
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            invoice_id = inv.id
        finally:
            db.close()

        # Create Payment Order
        order_resp = await client.post(
            "/api/v1/payments/orders",
            headers=headers,
            json={"invoice_id": str(invoice_id)},
        )
        assert order_resp.status_code == 201
        data = order_resp.json()
        assert data["order_id"].startswith("order_")
        assert data["amount"] == 4900  # $49.00 converted to 4900 minor units
        assert data["currency"] == "USD"
        assert data["invoice_id"] == str(invoice_id)
        assert "key_id" in data


@pytest.mark.asyncio
async def test_invoice_ownership_verification():
    """Module 2: Ensure a tenant cannot create a payment order for another tenant's invoice."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant A
        reg_a = await client.post("/api/v1/auth/register", json={
            "email": f"tenant_a_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Tenant A",
        })
        token_a = reg_a.json()["access_token"]
        user_a_id = uuid.UUID(reg_a.json()["user"]["id"])

        # Tenant B
        reg_b = await client.post("/api/v1/auth/register", json={
            "email": f"tenant_b_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Tenant B",
        })
        token_b = reg_b.json()["access_token"]

        # Create invoice for Tenant A
        db = SessionLocal()
        try:
            sub_a = db.scalars(select(Subscription).where(Subscription.user_id == user_a_id)).first()
            inv_a = Invoice(
                user_id=user_a_id,
                subscription_id=sub_a.id,
                invoice_number=f"INV-A-{uuid.uuid4().hex[:4].upper()}",
                status="open",
                currency="USD",
                subtotal=Decimal("29.00"),
                tax=Decimal("0.00"),
                total=Decimal("29.00"),
                issued_at=datetime.now(timezone.utc),
            )
            db.add(inv_a)
            db.commit()
            db.refresh(inv_a)
            invoice_a_id = inv_a.id
        finally:
            db.close()

        # Tenant B tries to create order for Tenant A's invoice
        resp = await client.post(
            "/api/v1/payments/orders",
            headers={"Authorization": f"Bearer {token_b}"},
            json={"invoice_id": str(invoice_a_id)},
        )
        assert resp.status_code == 403
        assert "permission" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_already_paid_invoice_rejection():
    """Module 2: Reject payment order creation on an already settled invoice."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"paid_inv_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Paid Invoice Tester",
        })
        token = reg.json()["access_token"]
        user_id = uuid.UUID(reg.json()["user"]["id"])

        db = SessionLocal()
        try:
            sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
            inv = Invoice(
                user_id=user_id,
                subscription_id=sub.id,
                invoice_number=f"INV-PAID-{uuid.uuid4().hex[:4].upper()}",
                status="paid",  # ALREADY PAID
                currency="USD",
                subtotal=Decimal("29.00"),
                tax=Decimal("0.00"),
                total=Decimal("29.00"),
                issued_at=datetime.now(timezone.utc),
                paid_at=datetime.now(timezone.utc),
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            invoice_id = inv.id
        finally:
            db.close()

        resp = await client.post(
            "/api/v1/payments/orders",
            headers={"Authorization": f"Bearer {token}"},
            json={"invoice_id": str(invoice_id)},
        )
        assert resp.status_code == 400
        assert "already paid" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_invalid_payment_signature():
    """Module 3: Reject payment verification when signature is forged or invalid."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"sig_invalid_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Signature Tester",
        })
        token = reg.json()["access_token"]

        resp = await client.post(
            "/api/v1/payments/verify",
            headers={"Authorization": f"Bearer {token}"},
            json={
                "razorpay_order_id": "order_fake123",
                "razorpay_payment_id": "pay_fake123",
                "razorpay_signature": "invalid_forged_signature_hex",
            },
        )
        assert resp.status_code == 400
        assert "invalid payment signature" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_valid_payment_signature_and_capture():
    """Module 3: Valid signature successfully captures payment and marks invoice as paid."""
    transport = ASGITransport(app=app)
    rzp_service = RazorpayService()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Register user
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"capture_user_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Capture Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(reg.json()["user"]["id"])

        # Create open invoice
        db = SessionLocal()
        try:
            sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
            inv = Invoice(
                user_id=user_id,
                subscription_id=sub.id,
                invoice_number=f"INV-CAP-{uuid.uuid4().hex[:4].upper()}",
                status="open",
                currency="USD",
                subtotal=Decimal("99.00"),
                tax=Decimal("0.00"),
                total=Decimal("99.00"),
                issued_at=datetime.now(timezone.utc),
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            invoice_id = inv.id
        finally:
            db.close()

        # 1. Create order
        order_resp = await client.post(
            "/api/v1/payments/orders",
            headers=headers,
            json={"invoice_id": str(invoice_id)},
        )
        assert order_resp.status_code == 201
        order_id = order_resp.json()["order_id"]

        # 2. Simulate Razorpay payment ID & generate cryptographically valid HMAC-SHA256 signature
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        valid_signature = rzp_service.generate_test_payment_signature(
            order_id=order_id,
            payment_id=payment_id,
        )

        # 3. Verify Payment
        verify_resp = await client.post(
            "/api/v1/payments/verify",
            headers=headers,
            json={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_signature,
            },
        )
        assert verify_resp.status_code == 200
        pay_data = verify_resp.json()
        assert pay_data["status"] == "captured"
        assert pay_data["razorpay_payment_id"] == payment_id
        assert pay_data["captured_at"] is not None

        # 4. Verify Invoice is marked paid in DB
        db = SessionLocal()
        try:
            updated_inv = db.get(Invoice, invoice_id)
            assert updated_inv.status == "paid"
            assert updated_inv.paid_at is not None
        finally:
            db.close()


@pytest.mark.asyncio
async def test_amount_mismatch_rejection():
    """Module 3: Reject payment verification if invoice amount was altered after order creation."""
    transport = ASGITransport(app=app)
    rzp_service = RazorpayService()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"amount_mismatch_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Mismatch Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(reg.json()["user"]["id"])

        db = SessionLocal()
        try:
            sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
            inv = Invoice(
                user_id=user_id,
                subscription_id=sub.id,
                invoice_number=f"INV-MIS-{uuid.uuid4().hex[:4].upper()}",
                status="open",
                currency="USD",
                subtotal=Decimal("50.00"),
                tax=Decimal("0.00"),
                total=Decimal("50.00"),
                issued_at=datetime.now(timezone.utc),
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            invoice_id = inv.id
        finally:
            db.close()

        # Create Order
        order_resp = await client.post("/api/v1/payments/orders", headers=headers, json={"invoice_id": str(invoice_id)})
        order_id = order_resp.json()["order_id"]

        # Alter invoice total maliciously behind the scenes
        db = SessionLocal()
        try:
            target_inv = db.get(Invoice, invoice_id)
            target_inv.total = Decimal("100.00")
            db.commit()
        finally:
            db.close()

        # Attempt verification
        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        valid_sig = rzp_service.generate_test_payment_signature(order_id, payment_id)

        resp = await client.post(
            "/api/v1/payments/verify",
            headers=headers,
            json={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
            },
        )
        assert resp.status_code == 400
        assert "amount mismatch" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_currency_mismatch_rejection():
    """Module 3: Reject payment verification if invoice currency does not match."""
    transport = ASGITransport(app=app)
    rzp_service = RazorpayService()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"curr_mismatch_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Currency Tester",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(reg.json()["user"]["id"])

        db = SessionLocal()
        try:
            sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
            inv = Invoice(
                user_id=user_id,
                subscription_id=sub.id,
                invoice_number=f"INV-CUR-{uuid.uuid4().hex[:4].upper()}",
                status="open",
                currency="USD",
                subtotal=Decimal("30.00"),
                tax=Decimal("0.00"),
                total=Decimal("30.00"),
                issued_at=datetime.now(timezone.utc),
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            invoice_id = inv.id
        finally:
            db.close()

        order_resp = await client.post("/api/v1/payments/orders", headers=headers, json={"invoice_id": str(invoice_id)})
        order_id = order_resp.json()["order_id"]

        # Alter invoice currency to EUR
        db = SessionLocal()
        try:
            target_inv = db.get(Invoice, invoice_id)
            target_inv.currency = "EUR"
            db.commit()
        finally:
            db.close()

        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        valid_sig = rzp_service.generate_test_payment_signature(order_id, payment_id)

        resp = await client.post(
            "/api/v1/payments/verify",
            headers=headers,
            json={
                "razorpay_order_id": order_id,
                "razorpay_payment_id": payment_id,
                "razorpay_signature": valid_sig,
            },
        )
        assert resp.status_code == 400
        assert "currency mismatch" in resp.json()["message"].lower()


@pytest.mark.asyncio
async def test_duplicate_payment_verification_idempotency():
    """Module 3: Submitting verification for an already captured payment returns captured record without double update."""
    transport = ASGITransport(app=app)
    rzp_service = RazorpayService()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"dup_ver_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Idempotent Verifier",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(reg.json()["user"]["id"])

        db = SessionLocal()
        try:
            sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
            inv = Invoice(
                user_id=user_id,
                subscription_id=sub.id,
                invoice_number=f"INV-DUP-{uuid.uuid4().hex[:4].upper()}",
                status="open",
                currency="USD",
                subtotal=Decimal("20.00"),
                tax=Decimal("0.00"),
                total=Decimal("20.00"),
                issued_at=datetime.now(timezone.utc),
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            invoice_id = inv.id
        finally:
            db.close()

        order_resp = await client.post("/api/v1/payments/orders", headers=headers, json={"invoice_id": str(invoice_id)})
        order_id = order_resp.json()["order_id"]

        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        valid_sig = rzp_service.generate_test_payment_signature(order_id, payment_id)

        # Verification 1
        resp1 = await client.post(
            "/api/v1/payments/verify",
            headers=headers,
            json={"razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": valid_sig},
        )
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "captured"

        # Verification 2 (Duplicate)
        resp2 = await client.post(
            "/api/v1/payments/verify",
            headers=headers,
            json={"razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": valid_sig},
        )
        assert resp2.status_code == 200
        assert resp2.json()["status"] == "captured"
        assert resp2.json()["id"] == resp1.json()["id"]


@pytest.mark.asyncio
async def test_unauthorized_payment_access():
    """Module 5: A tenant cannot view another tenant's payment history."""
    transport = ASGITransport(app=app)
    rzp_service = RazorpayService()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        # Tenant 1 creates and verifies payment
        reg1 = await client.post("/api/v1/auth/register", json={
            "email": f"owner_tenant_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Owner Tenant",
        })
        token1 = reg1.json()["access_token"]
        user1_id = uuid.UUID(reg1.json()["user"]["id"])

        # Tenant 2
        reg2 = await client.post("/api/v1/auth/register", json={
            "email": f"snooper_tenant_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "Snooper Tenant",
        })
        token2 = reg2.json()["access_token"]

        db = SessionLocal()
        try:
            sub = db.scalars(select(Subscription).where(Subscription.user_id == user1_id)).first()
            inv = Invoice(
                user_id=user1_id,
                subscription_id=sub.id,
                invoice_number=f"INV-OWN-{uuid.uuid4().hex[:4].upper()}",
                status="open",
                currency="USD",
                subtotal=Decimal("15.00"),
                tax=Decimal("0.00"),
                total=Decimal("15.00"),
                issued_at=datetime.now(timezone.utc),
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            invoice_id = inv.id
        finally:
            db.close()

        order_resp = await client.post("/api/v1/payments/orders", headers={"Authorization": f"Bearer {token1}"}, json={"invoice_id": str(invoice_id)})
        order_id = order_resp.json()["order_id"]

        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        sig = rzp_service.generate_test_payment_signature(order_id, payment_id)

        v_resp = await client.post(
            "/api/v1/payments/verify",
            headers={"Authorization": f"Bearer {token1}"},
            json={"razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": sig},
        )
        assert v_resp.status_code == 200
        payment_uuid = v_resp.json()["id"]

        # Tenant 2 tries to access payment directly
        resp_direct = await client.get(
            f"/api/v1/payments/{payment_uuid}",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert resp_direct.status_code == 403

        # Tenant 2 tries to access invoice payments
        resp_inv = await client.get(
            f"/api/v1/invoices/{invoice_id}/payments",
            headers={"Authorization": f"Bearer {token2}"},
        )
        assert resp_inv.status_code == 403


@pytest.mark.asyncio
async def test_payment_history_endpoints():
    """Module 5: Tenant can list payments for an invoice and inspect individual payment."""
    transport = ASGITransport(app=app)
    rzp_service = RazorpayService()

    async with AsyncClient(transport=transport, base_url="http://test") as client:
        reg = await client.post("/api/v1/auth/register", json={
            "email": f"history_tenant_{uuid.uuid4().hex[:8]}@meterflow.io",
            "password": "Password123!",
            "display_name": "History Tenant",
        })
        token = reg.json()["access_token"]
        headers = {"Authorization": f"Bearer {token}"}
        user_id = uuid.UUID(reg.json()["user"]["id"])

        db = SessionLocal()
        try:
            sub = db.scalars(select(Subscription).where(Subscription.user_id == user_id)).first()
            inv = Invoice(
                user_id=user_id,
                subscription_id=sub.id,
                invoice_number=f"INV-HIST-{uuid.uuid4().hex[:4].upper()}",
                status="open",
                currency="USD",
                subtotal=Decimal("40.00"),
                tax=Decimal("0.00"),
                total=Decimal("40.00"),
                issued_at=datetime.now(timezone.utc),
            )
            db.add(inv)
            db.commit()
            db.refresh(inv)
            invoice_id = inv.id
        finally:
            db.close()

        # Create and verify payment
        order_resp = await client.post("/api/v1/payments/orders", headers=headers, json={"invoice_id": str(invoice_id)})
        order_id = order_resp.json()["order_id"]

        payment_id = f"pay_{uuid.uuid4().hex[:12]}"
        sig = rzp_service.generate_test_payment_signature(order_id, payment_id)

        v_resp = await client.post(
            "/api/v1/payments/verify",
            headers=headers,
            json={"razorpay_order_id": order_id, "razorpay_payment_id": payment_id, "razorpay_signature": sig},
        )
        payment_uuid = v_resp.json()["id"]

        # GET /payments/{payment_id}
        p_resp = await client.get(f"/api/v1/payments/{payment_uuid}", headers=headers)
        assert p_resp.status_code == 200
        assert p_resp.json()["id"] == payment_uuid
        assert p_resp.json()["status"] == "captured"

        # GET /invoices/{invoice_id}/payments
        inv_p_resp = await client.get(f"/api/v1/invoices/{invoice_id}/payments", headers=headers)
        assert inv_p_resp.status_code == 200
        payments_list = inv_p_resp.json()
        assert len(payments_list) >= 1
        assert payments_list[0]["id"] == payment_uuid
