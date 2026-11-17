# MeterFlow — Project Master Status, Architecture & Roadmap

> **Document Purpose:** Handover and engineering roadmap for MeterFlow.  
> Share this file with ChatGPT, teammates, or other AI agents to immediately understand what has already been built, verified, and what features remain to be implemented.

---

## 1. Executive Summary

* **Project Name:** MeterFlow
* **Domain:** Backend API Usage, Rate Limiting, and Subscription Billing Management Engine.
* **Technology Stack:**
  * **Language:** Python 3.13 (supports Python 3.12+)
  * **Web Framework:** FastAPI (with Uvicorn ASGI server)
  * **Database:** PostgreSQL 16 (Hosted on Neon Cloud with SSL / compatible with local PostgreSQL)
  * **ORM & Database Driver:** SQLAlchemy 2.0 + Psycopg 3 (`psycopg[binary]`)
  * **Migrations:** Alembic
  * **Validation & Settings:** Pydantic v2 + `pydantic-settings` + `email-validator`
  * **Data Processing:** Pandas (for dataset transformation)
  * **Testing:** Pytest (54/54 automated tests passing) + HTTPX
* **Current Status:** **Phase 1 (Database Architecture & Data Integration)**, **Phase 2 (Python Backend Foundation)**, **Phase 3 (Authentication & API Key Management)**, **Phase 4 (High-Performance Rate Limiting & Quotas)**, **Phase 5 (Daily Aggregations & Billing Engine)**, and **Phase 6 (Payment Gateway & Webhook Integration - Razorpay Test Mode)** are **100% Complete & Verified** (54/54 automated tests passing).

---

## 2. What Is Already Built & Verified (Phases 1, 2, 3 & 4)

### A. Database Architecture (All 10 Relational Tables Live)
The database schema is fully initialized in PostgreSQL with primary keys, foreign keys, and constraints:
1. **`users`:** Developer customer accounts (UUID PK, unique lowercase email, password hash, status check).
2. **`api_keys`:** Tenant API credentials (UUID PK, foreign key to users, display prefix, unique 64-char SHA-256 hex hash check).
3. **`subscription_plans`:** Catalog pricing tiers (Free `$0.00`, Pro `$29.00`, Enterprise `$299.00`, currency `USD`).
4. **`subscriptions`:** Tenant subscriptions linking users to plans with 30-day billing period bounds and composite ownership unique keys.
5. **`usage_events`:** Core immutable ledger recording HTTP requests, status codes, latency in ms, payload bytes, and unique source keys.
6. **`usage_daily`:** Pre-aggregated daily rollup dimensions for fast reporting.
7. **`usage_quotas`:** Tier quotas (e.g. daily/monthly request limits with hard/soft limit flags).
8. **`invoices`:** Financial records with currency, subtotal, tax, total, and status lifecycle (`draft`, `open`, `paid`, `void`).
9. **`invoice_items`:** Itemized invoice line items with cascading foreign keys to invoices.
10. **`audit_logs`:** System audit trail storing JSONB metadata and actor user IDs.

### B. Security, Bcrypt & Cryptographic Key Generation
* **Bcrypt Password Hashing:** User passwords securely hashed with Bcrypt (cost factor 12) via `app.core.security.hash_password`.
* **JWT Access Tokens:** Signed with HMAC-SHA256 (`HS256`), 24-hour expiration, containing standard `sub` (user UUID), issuer, and claims.
* **CSPRNG Key Generation:** API keys generated via Python's `secrets.token_urlsafe(32)` formatted as `mf_live_<random>`.
* **Zero Plaintext Secrets:** The database **never** stores plaintext keys. It stores strictly 64-character lowercase SHA-256 hashes matching `CHECK (key_hash ~ '^[0-9a-f]{64}$')`. Plaintext is returned **ONLY ONCE** upon creation.
* **Display Prefix:** Stores a non-secret prefix (e.g. `mf_live_nIbXZPXs`) for user identification.

### C. Seed & Demo Tenants
Provisioned 3 realistic demo accounts with active subscriptions:
* **TechNova Solutions** (`admin@technova.io`) $\rightarrow$ Enterprise Plan (`$299.00/mo`)
* **CloudSphere Technologies** (`engineering@cloudsphere.dev`) $\rightarrow$ Pro Plan (`$29.00/mo`)
* **DataBridge Systems** (`ops@databridge.net`) $\rightarrow$ Free Plan (`$0.00/mo`)

### D. Dataset Cleaning & Ingestion Pipeline
* Processed the raw Hugging Face web-server-logs dataset (`data/raw/access_logs.csv` — 5,000 raw lines).
* Filtered out **1,065 static assets** (`/static/`, `.png`, `.js`, `.css`) and **1,709 website pages** (`/about`, `/pricing`, `/docs`).
* Produced cleaned output: `data/processed/api_usage_events.csv` (2,226 approved API records).
* Ingested **1,000 verified events** into PostgreSQL across 10 batches of 100 rows with `ON CONFLICT (source_record_key) DO NOTHING` idempotency.

### E. Layered Backend Software Architecture
* **FastAPI Application (`app/main.py`):** Configured with CORS, request logging, execution timing (`X-Process-Time`), API Gateway verification middleware, centralized exception handlers, and interactive Swagger UI (`/docs`).
* **Repository Pattern (`app/repositories/`):** Dedicated classes for `UserRepository`, `PlanRepository`, `UsageRepository`, and `APIKeyRepository` with eager loading (`selectinload` / `joinedload`) preventing N+1 queries.
* **Service Layer (`app/services/`):** Business logic classes for `UserService`, `PlanService`, `UsageService`, `AuthService`, and `APIKeyService`.
* **Pydantic Validation Schemas (`app/schemas/`):** Strict models for users, auth, API keys, plans, usage events, and reusable `Page[T]` pagination.

### F. Working Endpoints Live
* `GET /api/v1/health`: System health and live database connection status.
* `POST /api/v1/auth/register`: Developer registration with Bcrypt hashing and auto-provisioned Free tier.
* `POST /api/v1/auth/login`: Developer authentication returning signed JWT token.
* `GET /api/v1/auth/me`: Authenticated developer profile with subscriptions and non-secret API keys.
* `GET /api/v1/api-keys`: Lists user API keys (prefixes, expiration, revocation status).
* `POST /api/v1/api-keys`: Creates new API key, returns plaintext secret once.
* `DELETE /api/v1/api-keys/{id}`: Revokes API key immediately.
* `GET /api/v1/gateway/verify`: Downstream verification test for API Gateway `X-API-Key` middleware.
* `GET /api/v1/users`: Paginated developer accounts (credentials excluded).
* `GET /api/v1/users/{user_id}`: Developer account details with active subscriptions & API key prefixes.
* `GET /api/v1/plans`: Active catalog subscription plans.
* `GET /api/v1/usage/summary`: Aggregated API usage metrics (total, success, failed, average latency, bytes).
* `GET /api/v1/usage/events`: Paginated real-time access events log with method/endpoint filters.

### G. Performance & Validation
* **Sub-millisecond queries:** `EXPLAIN ANALYZE` on indexed queries runs in **0.07ms – 0.15ms**.
* **Test Suite:** **30 automated tests passing** in `tests/` (`100%` pass rate).
* **Postman Collection:** Ready in `postman/MeterFlow-Phase-3.postman_collection.json`.

### H. Terminal Management CLI & Shortcuts
* **Unified CLI (`cli.py` / `meterflow.bat`):** Complete command-line interface with interactive control panel and direct subcommands:
  * `meterflow` : Interactive terminal dashboard menu
  * `meterflow server` : Starts FastAPI uvicorn server with auto-reload
  * `meterflow status` : PostgreSQL connectivity & table row counts
  * `meterflow users` : Lists registered tenants, subscriptions & key prefixes
  * `meterflow plans` : Lists subscription tiers & billing intervals
  * `meterflow usage` : Live analytics, latency metrics & HTTP method distribution
  * `meterflow test` : Runs the 30 Pytest tests
  * `meterflow validate` : Runs constraints audit & query benchmarks
  * `meterflow transform` : Data cleaning & normalizer
  * `meterflow import` : Batch ingestion into database
* **Terminal Guide:** Detailed guide in [`TERMINAL_GUIDE.md`](file:///d:/Dhruv/TERMINAL_GUIDE.md).

### I. Distributed Redis Rate Limiting & Quota Enforcement (Phase 4)
* **Algorithms Implemented:**
  * **Sliding Window Log:** Redis Sorted Set (`ZSET`) algorithm with sub-millisecond precision, completely preventing boundary-reset spikes.
  * **Token Bucket:** Continuous fractional token replenishment allowing controlled burst capacity.
* **Tier Limit Enforcement:**
  * **Free Tier:** 60 req/min (10,000 monthly hard quota)
  * **Pro Tier:** 300 req/min (100,000 monthly quota)
  * **Enterprise Tier:** 1,200 req/min (1,000,000 monthly quota)
* **HTTP 429 & RFC Headers:** Injects `X-RateLimit-Limit`, `X-RateLimit-Remaining`, `X-RateLimit-Reset` into all Gateway responses. When limit is exceeded, returns HTTP 429 (`Too Many Requests`) with `Retry-After: <seconds>` header.
* **Graceful Degradation:** Redis client automatically falls back to in-memory `fakeredis` if an external Redis instance is unavailable, ensuring 100% offline & local test compatibility.

### J. Daily Aggregations & Billing Engine (Phase 5)
* **Background Rollup Worker:**
  * Aggregates raw, high-volume `usage_events` into dimensional `usage_daily` table grouped by `(usage_date, subscription_id, api_key_id, endpoint, http_method)`.
  * Computes total requests, success count (HTTP 2xx), error count (HTTP 4xx/5xx), total response bytes, total latency, and average latency.
  * 100% idempotent via PostgreSQL `ON CONFLICT (...) DO UPDATE`.
  * Upserted **724 dimensional records** across 16 calendar days from 1,000 raw events in **1,722 ms**.
  * Standalone CLI worker runnable via `meterflow rollup` or `python scripts/run_aggregation.py`.
* **Invoicing & Tiered Overage Engine:**
  * Computes monthly subscription base price (Free: $0.00, Pro: $29.00, Enterprise: $299.00).
  * Evaluates usage against plan allowances (Free: 10,000 reqs, Pro: 100,000 reqs, Enterprise: 1,000,000 reqs).
  * Calculates tiered overage line items with unit pricing (Pro: $0.010/1,000 units, Enterprise: $0.005/1,000 units).
  * Generates sequential invoice identifiers (`INV-YYYYMM-XXXX`) and persists records in `invoices` and `invoice_items`.
  * Settle and timestamp payments transitions status from `open` to `paid`.
* **Phase 5 Endpoints:**
  * `GET /api/v1/billing/preview`: Real-time accruals for current billing cycle.
  * `POST /api/v1/billing/invoices/generate`: Generates itemized invoice with line items.
  * `GET /api/v1/billing/invoices`: Lists historical invoices for authenticated developer.
  * `GET /api/v1/billing/invoices/{id}`: Detailed invoice breakdown with line items.
  * `POST /api/v1/billing/invoices/{id}/pay`: Settle invoice and record payment timestamp.
  * `POST /api/v1/billing/rollup`: Trigger daily aggregation rollup on demand.

### K. Payment Gateway & Webhook Integration (Phase 6 - Razorpay Test Mode)
* **Razorpay Test Order Generation:**
  * Authenticates customer and strictly verifies target invoice ownership and payable state.
  * Rejects already-paid invoices (HTTP 400 Bad Request).
  * Automatically converts Decimal monetary amounts to integer minor units (paise/cents).
  * Stores order references in PostgreSQL `payments` table and avoids duplicate active pending orders.
  * Exposed via `POST /api/v1/payments/orders`.
* **Cryptographic Signature Verification:**
  * Computes HMAC-SHA256 signature of `order_id + "|" + payment_id` with `RAZORPAY_KEY_SECRET`.
  * Verifies payment amount and currency match the invoice total.
  * Transactionally transitions `payment.status` to `captured` and `invoice.status` to `paid`.
  * Idempotency guarantee: re-verifying an already captured payment returns clean status without double-billing.
  * Exposed via `POST /api/v1/payments/verify`.
* **Asynchronous Webhook Ingestion:**
  * Validates raw body HMAC-SHA256 signature using `X-Razorpay-Signature`.
  * Stores all incoming gateway event IDs in `payment_webhook_events` to enforce strict idempotency (duplicate events return `status="ignored"`).
  * Handles `payment.authorized`, `payment.captured`, `payment.failed` (capturing error codes), and `refund.processed` (updating `amount_refunded`).
  * **Late Reversal Protection:** Guarantees that out-of-order or late `payment.failed` webhooks can never reverse an already `captured` or `refunded` payment.
  * Transaction rollback guarantees safe atomic updates on unhandled database errors.
  * Exposed via `POST /api/v1/payments/webhooks/razorpay`.
* **Payment History & Isolation:**
  * `GET /api/v1/payments/{payment_id}`: Retrieves payment details (restricted to payment owner).
  * `GET /api/v1/invoices/{invoice_id}/payments`: Lists payment attempts and settlements for an invoice.
  * Cross-tenant access strictly blocked with HTTP 403 Forbidden.

---

## 3. What Is Left To Build (Future Phases Roadmap)

The following modules remain to be built to make MeterFlow a fully production-ready metering and billing platform:

### Phase 7: Containerization, Stress Testing & Production Deployment (Next Step)
- [ ] **Production Docker Infrastructure:**
  - Multi-stage `Dockerfile` (FastAPI app with Uvicorn).
  - `docker-compose.yml` orchestrating FastAPI + PostgreSQL 16 + Redis.
- [ ] **High-Volume Stress & Concurrency Testing:**
  - Load testing script (Locust or Async HTTPX streamer) simulating 1,000+ to 10,000+ requests/second.
  - Benchmark Redis rate limiter under heavy concurrency and evaluate p95/p99 latency.
  - Verify PostgreSQL connection pool resilience under load.

---

### Phase 8: Tenant Alerts, CI/CD Pipeline & Monitoring
- [ ] **Tenant Alerts & Notification Webhooks:**
  - Dispatch webhooks to developers when they reach 80%, 90%, and 100% of their plan quota.
  - Retry logic with exponential backoff for failed webhook deliveries.
- [ ] **CI/CD Pipeline:**
  - GitHub Actions workflow running `pytest`, code formatting (`ruff` / `black`), and linting.
- [ ] **Prometheus & Grafana Metrics:**
  - Expose `/metrics` Prometheus endpoint for API latency, rate limit drops, and DB pool stats.
  - GitHub Actions workflow running `pytest`, code formatting (`ruff` / `black`), and linting.

---

## 4. Current File Tree

```text
meterflow/ (D:\Dhruv)
├── app/
│   ├── __init__.py
│   ├── main.py                  # FastAPI app entrypoint, CORS, exception handlers
│   ├── core/
│   │   ├── config.py            # Pydantic-settings configuration & driver normalizer
│   │   ├── database.py          # SQLAlchemy 2.0 Engine, QueuePool & get_db dependency
│   │   └── exceptions.py        # Centralized domain exceptions (EntityNotFoundError, etc.)
│   ├── models/                  # SQLAlchemy 2.0 ORM models
│   │   ├── __init__.py
│   │   ├── user.py              # User model (users table)
│   │   ├── api_key.py           # APIKey model (api_keys table)
│   │   ├── plan.py              # SubscriptionPlan model (subscription_plans table)
│   │   ├── subscription.py      # Subscription model (subscriptions table)
│   │   ├── usage_event.py       # UsageEvent model (usage_events table)
│   │   ├── usage_daily.py       # UsageDaily model (usage_daily aggregation table)
│   │   └── invoice.py           # Invoice & InvoiceItem models (invoices & invoice_items)
│   ├── schemas/                 # Pydantic v2 validation models
│   │   ├── __init__.py
│   │   ├── common.py            # Reusable Page[T] and PaginationParams
│   │   ├── user.py              # UserResponse and UserDetailResponse
│   │   ├── auth.py              # UserRegisterRequest, TokenResponse
│   │   ├── api_key.py           # APIKeyCreateRequest, APIKeyResponse
│   │   ├── plan.py              # SubscriptionPlanResponse
│   │   ├── usage.py             # UsageEventResponse, UsageSummaryResponse, HealthResponse
│   │   ├── billing.py           # InvoiceResponse, BillingPreviewResponse, GenerateInvoiceRequest
│   │   └── payment.py           # PaymentOrderResponse, PaymentVerifyRequest, PaymentResponse
│   ├── repositories/            # Data access layer (decoupled queries)
│   │   ├── __init__.py
│   │   ├── user_repository.py
│   │   ├── api_key_repository.py
│   │   ├── plan_repository.py
│   │   ├── usage_repository.py
│   │   ├── invoice_repository.py
│   │   └── payment_repository.py # Payment & webhook idempotency queries
│   ├── services/                # Business logic layer
│   │   ├── __init__.py
│   │   ├── user_service.py
│   │   ├── auth_service.py
│   │   ├── api_key_service.py
│   │   ├── plan_service.py
│   │   ├── usage_service.py
│   │   ├── rate_limiter.py      # Sliding Window Log & Token Bucket algorithms
│   │   ├── quota_service.py     # Plan quota checking & tier lookup
│   │   ├── aggregation_service.py # Daily rollup aggregation engine
│   │   ├── billing_service.py   # Tiered overage & invoicing engine
│   │   ├── razorpay_service.py  # Razorpay gateway & HMAC-SHA256 signature verification
│   │   └── payment_service.py   # Payment orchestration, settlement & webhook processing
│   ├── api/
│   │   ├── dependencies.py      # FastAPI DI providers
│   │   └── routes/              # HTTP Route Controllers
│   │       ├── __init__.py
│   │       ├── health.py        # GET /api/v1/health
│   │       ├── auth.py          # POST /api/v1/auth/register, /login, GET /me
│   │       ├── api_keys.py      # GET, POST, DELETE /api/v1/api-keys
│   │       ├── gateway.py       # GET /api/v1/gateway/verify (Rate limited)
│   │       ├── users.py         # GET /api/v1/users, GET /api/v1/users/{id}
│   │       ├── plans.py         # GET /api/v1/plans
│   │       ├── usage.py         # GET /api/v1/usage/summary, /usage/events
│   │       ├── billing.py       # GET /preview, POST /invoices/generate, /pay, /rollup
│   │       └── payments.py      # POST /orders, /verify, /webhooks/razorpay, GET /{id}
│   └── middleware/
│       ├── __init__.py
│       ├── request_logging.py   # Request logging and X-Process-Time calculation
│       └── rate_limit_middleware.py # Distributed Redis rate limiter & RFC headers
├── database/
│   ├── schema.sql               # PostgreSQL 10 tables DDL
│   ├── payments_schema.sql      # Phase 6 payments & webhook idempotency tables
│   ├── seed.sql                 # Sample developers and plans SQL
│   ├── indexes.sql              # Performance query indexes
│   └── views.sql                # Analytical views
├── data/
│   ├── raw/
│   │   └── access_logs.csv      # Raw Hugging Face access logs (5,000 records)
│   ├── processed/
│   │   └── api_usage_events.csv # 2,226 cleaned API requests
│   └── reports/
│       └── import_report.json   # Transformation & ingestion statistical report
├── scripts/
│   ├── apply_schema.py          # Applies schema.sql to PostgreSQL
│   ├── apply_phase6_schema.py   # Applies payments_schema.sql safely
│   ├── create_demo_users.py     # Provisions 3 demo users and hashes API keys
│   ├── transform_dataset.py     # Cleans CSV and attaches tenant IDs
│   ├── import_usage_events.py   # Ingests batches into PostgreSQL with deduplication
│   ├── run_aggregation.py       # Aggregates raw usage_events into usage_daily
│   ├── validate_import.py       # Runs 8-point ingestion verification
│   ├── final_validation.py      # Audits schema, constraints, and EXPLAIN ANALYZE
│   └── check_status.py          # Live verification dashboard
├── postman/
│   ├── MeterFlow-Phase-2.postman_collection.json
│   ├── MeterFlow-Phase-3.postman_collection.json
│   ├── MeterFlow-Phase-4.postman_collection.json
│   └── MeterFlow-Phase-5.postman_collection.json
├── docs/
│   ├── BACKEND_ARCHITECTURE.md
│   ├── API_DOCUMENTATION.md
│   ├── PAYMENT_INTEGRATION.md
│   ├── PHASE_6_COMPLETION_REPORT.md
│   ├── PHASE_2_SETUP.md
│   ├── DATABASE_DESIGN.md
│   ├── DATASET_ANALYSIS.md
│   └── ER_DIAGRAM.md
├── tests/
│   ├── test_health.py
│   ├── test_auth.py
│   ├── test_api_keys.py
│   ├── test_gateway_middleware.py
│   ├── test_rate_limiter.py
│   ├── test_billing.py
│   ├── test_payments.py
│   ├── test_payment_webhooks.py
│   ├── test_users.py
│   ├── test_plans.py
│   ├── test_usage.py
│   ├── test_database_models.py
│   └── test_demo_users.py
├── tests/
│   ├── test_health.py
│   ├── test_auth.py
│   ├── test_api_keys.py
│   ├── test_gateway_middleware.py
│   ├── test_rate_limiter.py
│   ├── test_billing.py
│   ├── test_users.py
│   ├── test_plans.py
│   ├── test_usage.py
│   ├── test_database_models.py
│   └── test_demo_users.py
├── alembic/
├── alembic.ini
├── requirements.txt
├── run_server.py                # Server startup script
├── start.bat                    # Windows one-click launcher
├── .env.example
├── .gitignore
└── README.md
```

---

## 6. How to Run the Project Right Now

### 1. Start the Server
```powershell
.venv\Scripts\python run_server.py
# Or double-click start.bat
```

### 2. View Swagger UI in Browser
Open: **`http://127.0.0.1:8000/docs`**

### 3. Run the Test Suite
```powershell
.venv\Scripts\python -m pytest tests -v
```

### 4. Check Live Database Status
```powershell
.venv\Scripts\python scripts\check_status.py
```
