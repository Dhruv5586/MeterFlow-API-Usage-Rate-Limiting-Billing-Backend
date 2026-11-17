# MeterFlow — Complete API Documentation (Phases 1 through 6)

MeterFlow provides RESTful HTTP endpoints for API usage monitoring, developer authentication, API key lifecycle management, and high-performance Redis rate-limiting gateway verification.

Interactive Swagger documentation is available at: **`http://127.0.0.1:8000/docs`**  
ReDoc is available at: **`http://127.0.0.1:8000/redoc`**

---

## High-Performance Rate Limiting & Quotas (Phase 4)

MeterFlow protects downstream microservices and enforces billing tier limits using distributed Redis rate limiting:
* **Algorithms Supported:**
  * **Sliding Window Log (Default):** Millisecond-precision rolling window via Redis Sorted Sets (`ZSET`). Eliminates boundary reset spikes.
  * **Token Bucket:** Smooth traffic replenishment with burst capacity allowances.
* **Tier Limits Enforced:**
  * **Free:** 60 requests / minute (10,000 monthly hard quota)
  * **Pro:** 300 requests / minute (100,000 monthly quota)
  * **Enterprise:** 1,200 requests / minute (1,000,000 monthly quota)
* **Standard RFC Rate Limit Response Headers:**
  * `X-RateLimit-Limit`: Maximum requests permitted within the 60-second window.
  * `X-RateLimit-Remaining`: Requests remaining in the current rolling window.
  * `X-RateLimit-Reset`: Seconds remaining until the quota window resets.
  * `Retry-After`: Injected when limit is exceeded (HTTP 429), specifying wait duration in seconds.
  * `X-Quota-Warning`: Injected when monthly consumption reaches 80% or more of tier threshold.

---

## Base URL
```text
http://127.0.0.1:8000/api/v1
```

---

## 1. Authentication & Accounts

### `POST /api/v1/auth/register`
Registers a new developer tenant account. Hashes password using Bcrypt, provisions a default Free subscription, and returns a signed JWT access token.

* **Request Body:**
```json
{
  "email": "developer@startup.io",
  "password": "StrongPassword123!",
  "display_name": "Startup Innovations"
}
```

* **Response (201 Created):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "20000000-0000-4000-8000-000000000004",
    "email": "developer@startup.io",
    "display_name": "Startup Innovations",
    "status": "active",
    "created_at": "2026-11-16T17:00:00Z",
    "updated_at": "2026-11-16T17:00:00Z"
  }
}
```

---

### `POST /api/v1/auth/login`
Authenticates developer credentials and returns a signed JWT access token.

* **Request Body:**
```json
{
  "email": "developer@startup.io",
  "password": "StrongPassword123!"
}
```

* **Response (200 OK):**
```json
{
  "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "token_type": "bearer",
  "expires_in": 86400,
  "user": {
    "id": "20000000-0000-4000-8000-000000000004",
    "email": "developer@startup.io",
    "display_name": "Startup Innovations",
    "status": "active",
    "created_at": "2026-11-16T17:00:00Z",
    "updated_at": "2026-11-16T17:00:00Z"
  }
}
```

---

### `GET /api/v1/auth/me`
Returns the authenticated developer's complete profile with active subscriptions and non-secret API keys.

* **Headers:**
  - `Authorization: Bearer <access_token>`

* **Response (200 OK):**
```json
{
  "id": "20000000-0000-4000-8000-000000000004",
  "email": "developer@startup.io",
  "display_name": "Startup Innovations",
  "status": "active",
  "created_at": "2026-11-16T17:00:00Z",
  "updated_at": "2026-11-16T17:00:00Z",
  "api_keys": [
    {
      "id": "40000000-0000-4000-8000-000000000005",
      "name": "Production Key",
      "key_prefix": "mf_live_4b8f3a91",
      "created_at": "2026-11-16T17:05:00Z",
      "expires_at": null,
      "last_used_at": null
    }
  ],
  "subscriptions": [
    {
      "id": "30000000-0000-4000-8000-000000000004",
      "plan_id": "00000000-0000-4000-8000-000000000001",
      "plan_code": "free",
      "plan_name": "Free",
      "status": "active",
      "current_period_start": "2026-11-16T17:00:00Z",
      "current_period_end": "2027-11-16T17:00:00Z"
    }
  ]
}
```

---

## 2. API Key Lifecycle Management

### `GET /api/v1/api-keys`
Lists all API keys created by the authenticated developer.

* **Headers:**
  - `Authorization: Bearer <access_token>`

* **Response (200 OK):**
```json
[
  {
    "id": "40000000-0000-4000-8000-000000000005",
    "name": "Production Key",
    "key_prefix": "mf_live_4b8f3a91",
    "created_at": "2026-11-16T17:05:00Z",
    "expires_at": "2027-02-14T17:05:00Z",
    "revoked_at": null,
    "last_used_at": "2026-11-16T17:10:00Z",
    "is_active": true
  }
]
```

---

### `POST /api/v1/api-keys`
Generates a new cryptographically random API key.
> **Security Notice:** The plaintext API key secret is shown **ONLY ONCE** upon creation. It is immediately hashed with SHA-256 and never stored in plaintext.

* **Headers:**
  - `Authorization: Bearer <access_token>`

* **Request Body:**
```json
{
  "name": "Production Microservice Key",
  "expires_in_days": 90
}
```

* **Response (201 Created):**
```json
{
  "id": "40000000-0000-4000-8000-000000000005",
  "name": "Production Microservice Key",
  "key_prefix": "mf_live_k9A23x8L",
  "api_key": "mf_live_k9A23x8L39485jfkdsjaf839420jsdakflj",
  "created_at": "2026-11-16T17:05:00Z",
  "expires_at": "2027-02-14T17:05:00Z",
  "message": "Store this API key safely in your application environment. You will not be able to view it again."
}
```

---

### `DELETE /api/v1/api-keys/{id}`
Immediately revokes an active API key. Any future request using this key will be rejected with HTTP 401 Unauthorized.

* **Headers:**
  - `Authorization: Bearer <access_token>`

* **Response (200 OK):**
```json
{
  "id": "40000000-0000-4000-8000-000000000005",
  "name": "Production Microservice Key",
  "revoked_at": "2026-11-16T17:15:00Z",
  "message": "API key has been successfully revoked and can no longer be used."
}
```

---

## 3. API Gateway Header Verification

### `GET /api/v1/gateway/verify`
Tests the API Gateway `X-API-Key` authentication middleware.

* **Headers:**
  - `X-API-Key: mf_live_...`

* **Response (200 OK - Authorized):**
```json
{
  "status": "authorized",
  "message": "API key successfully verified by MeterFlow API Gateway.",
  "key_id": "40000000-0000-4000-8000-000000000005",
  "key_name": "Production Microservice Key",
  "key_prefix": "mf_live_k9A23x8L",
  "user_id": "20000000-0000-4000-8000-000000000004",
  "user_email": "developer@startup.io",
  "user_display_name": "Startup Innovations"
}
```

* **Response (401 Unauthorized - Missing / Invalid / Revoked):**
```json
{
  "error": "Unauthorized",
  "message": "API key was revoked on 2026-11-16T17:15:00Z and can no longer be used.",
  "path": "/api/v1/gateway/verify"
}
```

---

## 4. System Health & Catalog

### `GET /api/v1/health`
Returns system uptime and live PostgreSQL connectivity.

### `GET /api/v1/plans`
Lists available billing tiers, pricing, monthly quotas, and rate limits.

### `GET /api/v1/usage/summary`
Returns global or per-tenant traffic metrics (total requests, avg latency, min/max latency, data transferred).

### `GET /api/v1/usage/events`
Returns paginated, filterable raw usage events.

---

## 5. Daily Aggregations & Billing Engine (Phase 5)

MeterFlow provides automated daily rollups from raw high-volume logs into `usage_daily`, coupled with an invoice engine supporting plan allowances, tiered overage calculation, and payment settlement.

### `GET /api/v1/billing/preview`
Returns real-time billing accruals for the authenticated tenant's current billing cycle.
* **Headers:** `Authorization: Bearer <access_token>`
* **Response (200 OK):**
```json
{
  "user_id": "20000000-0000-4000-8000-000000000001",
  "plan_name": "Free Tier",
  "period_start": "2026-11-01",
  "period_end": "2026-11-30",
  "total_requests": 341,
  "quota_allowance": 10000,
  "overage_requests": 0,
  "base_price": 0.00,
  "overage_price_per_unit": 0.0000,
  "overage_fee": 0.00,
  "estimated_subtotal": 0.00,
  "estimated_tax": 0.00,
  "estimated_total": 0.00,
  "currency": "USD"
}
```

---

### `POST /api/v1/billing/invoices/generate`
Generates and finalizes an itemized invoice for the tenant based on aggregated usage, base plan price, and tiered overages.
* **Headers:** `Authorization: Bearer <access_token>`
* **Request Body (Optional):**
```json
{
  "period_start": "2026-11-01",
  "period_end": "2026-11-30"
}
```
* **Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "invoice_number": "INV-202611-0001",
  "user_id": "20000000-0000-4000-8000-000000000001",
  "subscription_id": "30000000-0000-4000-8000-000000000001",
  "status": "open",
  "currency": "USD",
  "subtotal": 0.00,
  "tax": 0.00,
  "total": 0.00,
  "period_start": "2026-11-01",
  "period_end": "2026-11-30",
  "due_date": "2026-12-15",
  "paid_at": null,
  "created_at": "2026-11-17T00:00:00Z",
  "items": [
    {
      "id": "660e8400-e29b-41d4-a716-446655440000",
      "invoice_id": "550e8400-e29b-41d4-a716-446655440000",
      "item_type": "subscription_base",
      "description": "Free Tier Base Subscription (2026-11-01 to 2026-11-30)",
      "quantity": 1,
      "unit_price": 0.00,
      "amount": 0.00
    }
  ]
}
```

---

### `GET /api/v1/billing/invoices`
Lists all invoices issued to the authenticated developer tenant.
* **Headers:** `Authorization: Bearer <access_token>`
* **Response (200 OK):**
```json
[
  {
    "id": "550e8400-e29b-41d4-a716-446655440000",
    "invoice_number": "INV-202611-0001",
    "user_id": "20000000-0000-4000-8000-000000000001",
    "subscription_id": "30000000-0000-4000-8000-000000000001",
    "status": "open",
    "currency": "USD",
    "subtotal": 0.00,
    "tax": 0.00,
    "total": 0.00,
    "period_start": "2026-11-01",
    "period_end": "2026-11-30",
    "due_date": "2026-12-15",
    "paid_at": null,
    "created_at": "2026-11-17T00:00:00Z"
  }
]
```

---

### `GET /api/v1/billing/invoices/{id}`
Retrieves a specific invoice with complete itemized breakdown of base subscription and tiered overage fees.
* **Headers:** `Authorization: Bearer <access_token>`
* **Response (200 OK):** Itemized `InvoiceDetailResponse` with line items.

---

### `POST /api/v1/billing/invoices/{id}/pay`
Simulates instant payment settlement for an invoice, transitioning status from `open` to `paid` and recording timestamp.
* **Headers:** `Authorization: Bearer <access_token>`
* **Response (200 OK):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "invoice_number": "INV-202611-0001",
  "status": "paid",
  "paid_at": "2026-11-17T00:30:00Z",
  "total": 0.00,
  "items": [...]
}
```

---

### `POST /api/v1/billing/rollup`
Triggers an idempotent background aggregation rollup from `usage_events` into `usage_daily`.
* **Headers:** `Authorization: Bearer <access_token>`
* **Query Parameters (Optional):** `?target_date=2026-11-16`
* **Response (200 OK):**
```json
{
  "status": "success",
  "message": "Daily usage aggregation completed successfully.",
  "statistics": {
    "target_date": "all",
    "events_processed": 1000,
    "daily_records_upserted": 724,
    "duration_ms": 1722.5
  }
}
```

---

## 6. Payment Gateway & Webhook Integration (Phase 6 - Razorpay Test Mode)

MeterFlow provides native payment gateway integration with Razorpay Test Mode for invoice checkout, cryptographic signature verification, and asynchronous webhook lifecycle processing.

### `POST /api/v1/payments/orders`
Initiates a Razorpay payment order for an open, payable invoice.
* **Headers:** `Authorization: Bearer <access_token>`
* **Request Body:**
```json
{
  "invoice_id": "550e8400-e29b-41d4-a716-446655440000"
}
```
* **Response (201 Created):**
```json
{
  "order_id": "order_N1K9J8h7g6F5d4",
  "amount": 2900,
  "currency": "USD",
  "key_id": "rzp_test_placeholder_key_id",
  "invoice_id": "550e8400-e29b-41d4-a716-446655440000",
  "invoice_number": "INV-202611-0001"
}
```

---

### `POST /api/v1/payments/verify`
Submits checkout credentials for server-side HMAC-SHA256 signature verification and invoice settlement.
* **Headers:** `Authorization: Bearer <access_token>`
* **Request Body:**
```json
{
  "razorpay_order_id": "order_N1K9J8h7g6F5d4",
  "razorpay_payment_id": "pay_P9O8I7u6Y5t4",
  "razorpay_signature": "f2d4e8..."
}
```
* **Response (200 OK):**
```json
{
  "id": "770e8400-e29b-41d4-a716-446655440000",
  "user_id": "20000000-0000-4000-8000-000000000001",
  "invoice_id": "550e8400-e29b-41d4-a716-446655440000",
  "razorpay_order_id": "order_N1K9J8h7g6F5d4",
  "razorpay_payment_id": "pay_P9O8I7u6Y5t4",
  "amount": 29.00,
  "currency": "USD",
  "status": "captured",
  "captured_at": "2026-11-17T00:50:00Z"
}
```

---

### `POST /api/v1/payments/webhooks/razorpay`
Ingests asynchronous webhook events dispatched by Razorpay.
* **Headers:** `X-Razorpay-Signature: <hmac_sha256_hex>`
* **Payload:** Raw Razorpay webhook JSON.
* **Response (200 OK):**
```json
{
  "status": "success",
  "message": "Processed event payment.captured",
  "event_id": "evt_12345",
  "event_type": "payment.captured"
}
```

---

### `GET /api/v1/payments/{payment_id}`
Returns details of a specific payment transaction for the authenticated developer.
* **Headers:** `Authorization: Bearer <access_token>`

---

### `GET /api/v1/invoices/{invoice_id}/payments`
Returns all payment order attempts and capture records for a specific invoice.
* **Headers:** `Authorization: Bearer <access_token>`

