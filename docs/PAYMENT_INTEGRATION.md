# MeterFlow — Razorpay Payment Gateway & Webhook Integration (Phase 6)

## 1. Overview

MeterFlow Phase 6 integrates the **Razorpay Test Mode** payment gateway directly with MeterFlow's billing and invoicing engine. It enables automated order generation from payable invoices, cryptographic payment signature validation, idempotent incoming webhook ingestion, and comprehensive audit history.

---

## 2. Environment Configuration

Razorpay parameters are managed via `pydantic-settings` in `app/core/config.py`:

```ini
# Razorpay Payment Gateway (Test Mode)
RAZORPAY_KEY_ID=rzp_test_YOUR_KEY_ID
RAZORPAY_KEY_SECRET=YOUR_KEY_SECRET
RAZORPAY_WEBHOOK_SECRET=YOUR_WEBHOOK_SECRET
```

> **Security Guarantee:** API keys and secrets are never committed to version control, logged in terminal output, or exposed in public API responses. Only `RAZORPAY_KEY_ID` (the public key) is returned to client checkout responses.

---

## 3. Monetary Precision & Minor Units

All monetary values are calculated internally using Python's `Decimal` type to prevent binary floating-point rounding errors. 

Amounts are converted into integer minor units for the Razorpay API:
* **USD / INR Conversion:** $1.00 = 100 minor units (cents / paise).
* Example: An invoice for **$29.00** converts to **2900** minor units.
* The conversion helper is provided by `RazorpayService.amount_to_minor_units(amount, currency)`.

---

## 4. API Endpoints

### 4.1 Payment Order Creation

`POST /api/v1/payments/orders`

Creates a Razorpay order linked to an active, payable invoice.

* **Headers:** `Authorization: Bearer <jwt_token>`
* **Request Body:**
```json
{
  "invoice_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

* **Validation Rules:**
  1. The authenticated user must own the target invoice (HTTP 403 Forbidden otherwise).
  2. The invoice must not already be in `paid`, `void`, or `uncollectible` status (HTTP 400 Bad Request if already paid).
  3. The invoice total must be strictly greater than $0.00.
  4. Reuses any existing active pending order for the invoice to prevent duplicate open orders.

* **Response (201 Created):**
```json
{
  "order_id": "order_a1b2c3d4e5f6g7h8",
  "amount": 2900,
  "currency": "USD",
  "key_id": "rzp_test_...",
  "invoice_id": "550e8400-e29b-41d4-a716-446655440000",
  "invoice_number": "INV-202611-0001"
}
```

---

### 4.2 Payment Signature Verification

`POST /api/v1/payments/verify`

Validates the client-submitted Razorpay Checkout response using server-side HMAC-SHA256 signature verification.

* **Headers:** `Authorization: Bearer <jwt_token>`
* **Request Body:**
```json
{
  "razorpay_order_id": "order_a1b2c3d4e5f6g7h8",
  "razorpay_payment_id": "pay_9876543210ab",
  "razorpay_signature": "e84f5c2...hex"
}
```

* **Verification Algorithm:**
$$\text{Expected Signature} = \text{HMAC-SHA256}(\text{order\_id} + "|" + \text{payment\_id}, \text{RAZORPAY\_KEY\_SECRET})$$

* **Transactional Operations:**
  1. Compares computed signature with client signature using constant-time `hmac.compare_digest`.
  2. Verifies that order amount and currency match the underlying invoice.
  3. Updates `payments.status` to `captured`, recording timestamp.
  4. Settle `invoices.status` to `paid`, recording `paid_at`.
  5. Strictly idempotent: re-verifying an already captured payment returns the record without double-processing.

* **Response (200 OK):**
```json
{
  "id": "660e8400-e29b-41d4-a716-446655440000",
  "user_id": "20000000-0000-4000-8000-000000000001",
  "invoice_id": "550e8400-e29b-41d4-a716-446655440000",
  "razorpay_order_id": "order_a1b2c3d4e5f6g7h8",
  "razorpay_payment_id": "pay_9876543210ab",
  "amount": 29.00,
  "currency": "USD",
  "status": "captured",
  "captured_at": "2026-11-17T00:50:00Z",
  "created_at": "2026-11-17T00:45:00Z",
  "updated_at": "2026-11-17T00:50:00Z"
}
```

---

### 4.3 Webhook Ingestion

`POST /api/v1/payments/webhooks/razorpay`

Ingests asynchronous lifecycle notifications directly from Razorpay.

* **Headers:** `X-Razorpay-Signature: <hmac_hex>`
* **Signature Verification:**
$$\text{Expected Signature} = \text{HMAC-SHA256}(\text{raw\_body\_bytes}, \text{RAZORPAY\_WEBHOOK\_SECRET})$$

* **Supported Events:**
  * `payment.authorized`: Marks payment as authorized if order is pending.
  * `payment.captured`: Captures payment and transitions invoice to `paid`.
  * `payment.failed`: Records error codes and failure descriptions.
  * `refund.created` / `refund.processed`: Updates status to `refunded` and logs `amount_refunded`.

* **Idempotency & Reversal Protection:**
  * Every event ID (`event_id`) is stored in `payment_webhook_events`. Duplicate events return `status="ignored"` immediately.
  * Late or out-of-order `payment.failed` events **cannot** reverse an already `captured` or `refunded` payment.

* **Response (200 OK):**
```json
{
  "status": "success",
  "message": "Processed event payment.captured",
  "event_id": "evt_abc123",
  "event_type": "payment.captured"
}
```

---

### 4.4 Payment History & Inspection

* `GET /api/v1/payments/{payment_id}`: Retrieves payment details. Restricted to tenant owner.
* `GET /api/v1/invoices/{invoice_id}/payments`: Lists all payment attempts and settlements for a specified invoice.

---

## 5. Relational Schema (`payments` & `payment_webhook_events`)

```sql
CREATE TABLE payments (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users (id) ON DELETE RESTRICT,
    invoice_id UUID NOT NULL REFERENCES invoices (id) ON DELETE RESTRICT,
    razorpay_order_id TEXT NOT NULL,
    razorpay_payment_id TEXT UNIQUE,
    razorpay_signature TEXT,
    amount NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    currency VARCHAR(3) NOT NULL DEFAULT 'USD',
    status TEXT NOT NULL DEFAULT 'created',
    method TEXT,
    error_code TEXT,
    error_description TEXT,
    captured_at TIMESTAMPTZ,
    refunded_at TIMESTAMPTZ,
    amount_refunded NUMERIC(12, 2) NOT NULL DEFAULT 0.00,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE payment_webhook_events (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    event_id TEXT NOT NULL UNIQUE,
    event_type TEXT NOT NULL,
    order_id TEXT,
    payment_id TEXT,
    payload JSONB NOT NULL DEFAULT '{}'::JSONB,
    status TEXT NOT NULL DEFAULT 'processed',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
```
