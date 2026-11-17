# MeterFlow — Complete Project Master Report & Operational Guide
**System Version:** v0.1.0  
**Status:** All Phases (1 through 6) & Step 18 Security Hardening 100% Complete & Verified  
**Date:** November 2026  
**Backend Architecture:** Pure Python 3.13, FastAPI, SQLAlchemy 2.0, PostgreSQL 16 (Neon), Redis / FakeRedis  

---

## 1. What is MeterFlow? (Explained in Simple Terms)

### The Real-World Problem
Imagine you create a software service (an API) that other developers and companies pay to use (like OpenAI, Stripe, or Twilio). 
Three big challenges immediately arise:
1. **Usage Metering:** How do you track every single time a customer calls your API, what endpoint they hit, how fast your server responded, and how much data was sent?
2. **Abuse & Rate Limiting:** How do you prevent one rogue script or malicious user from sending 1,000 requests per second and crashing your servers for everyone else?
3. **Usage-Based Invoicing & Payments:** How do you charge customers fairly at the end of the month based on their plan (e.g. Free gets 10k requests, Pro gets 100k requests for $29/mo), calculate extra charges for overages (e.g. $0.01 per 1,000 extra requests), and collect the money via a payment gateway like Razorpay?

### The Solution: MeterFlow
**MeterFlow is the complete, enterprise-grade backend engine that handles all of this automatically.** 
It sits between clients and your API services like a smart digital electricity meter, security gatekeeper, and automated billing department.

```
[ Client Application / Postman / Developer ]
                  │
                  ▼
   ┌───────────────────────────────┐
   │    MeterFlow Security &       │  ◄── 1. Checks Security Headers & IP Rate Limits
   │    Authentication Barrier     │
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │      API Gateway & Key        │  ◄── 2. Authenticates X-API-Key
   │      Verification Layer       │  ◄── 3. Enforces Redis Rate Limits (60/300/1200 req/min)
   └──────────────┬────────────────┘  ◄── 4. Checks Monthly Quota (Warns at 80%, cuts off at 100%)
                  │
                  ▼
   ┌───────────────────────────────┐
   │     Usage Event Tracker       │  ◄── 5. Records latency, status code & payload size
   │    (usage_events ledger)      │
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │    Daily Aggregation Rollup   │  ◄── 6. Nightly worker summarizes raw logs into usage_daily
   │         Worker Engine         │
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │   Automated Invoicing Engine  │  ◄── 7. Calculates base plan fee + tiered overages
   │   (INV-YYYYMM-XXXX lifecycle) │
   └──────────────┬────────────────┘
                  │
                  ▼
   ┌───────────────────────────────┐
   │  Razorpay Payment & Webhook   │  ◄── 8. Creates orders, verifies signatures, handles
   │       Settlement Engine       │         payment.captured & refund webhooks idempotently
   └───────────────────────────────┘
```

---

## 2. Key Modules Explained in Simple Words

### A. Authentication & User Management (`app/api/routes/auth.py`)
- **What it does:** Allows developers to register an account, log in, and see their profile.
- **How it works:**
  - Passwords are never saved as plain text. They are hashed using **Bcrypt (cost factor 12)** with a unique cryptographic salt.
  - Upon logging in, the server issues a **JWT (JSON Web Token)** that expires after 24 hours. The client attaches this token (`Bearer <token>`) to access private endpoints.
  - New users are automatically provisioned with an active **Free Tier subscription**.

### B. Bank-Grade API Key Management (`app/api/routes/api_keys.py`)
- **What it does:** Allows customers to generate and revoke API keys (like `mf_live_xK9...`) to authenticate backend scripts.
- **How it works:**
  - Keys are generated using Python's cryptographically secure pseudo-random number generator (`secrets.token_urlsafe(32)`).
  - **Zero Plaintext Storage:** The raw key is shown to the user **exactly once** upon creation. MeterFlow only saves a 64-character SHA-256 cryptographic hash in PostgreSQL. Even if an attacker steals the entire database, they cannot reverse-engineer the API keys.
  - Keys can be instantly revoked with one click or API call.

### C. Security Hardening Middleware (`app/middleware/`)
- **Security Headers (`security_headers.py`):** Automatically injects OWASP headers (`X-Content-Type-Options: nosniff`, `X-Frame-Options: DENY`, `Referrer-Policy`, and `Content-Security-Policy`) into every HTTP response to shield users from clickjacking, MIME sniffing, and cross-site scripting.
- **Auth IP Throttling (`auth_rate_limit.py`):** Protects `/auth/login` and `/auth/register` by limiting requests to 10 per minute per IP address. It includes safe proxy resolution so attackers cannot bypass rate limits by spoofing `X-Forwarded-For` headers.

### D. High-Performance Rate Limiter (`app/services/rate_limiter.py`)
- **What it does:** Prevents abuse and enforces plan speed limits:
  - **Free Plan:** 60 requests / minute
  - **Pro Plan:** 300 requests / minute
  - **Enterprise Plan:** 1,200 requests / minute
- **How it works:**
  - **Sliding Window Log:** Uses Redis Sorted Sets (`ZSET`) to count requests over the last 60 rolling seconds. This completely eliminates boundary-burst exploits where a user sends double their quota across a minute boundary.
  - **Standard Headers:** Emits `X-RateLimit-Limit`, `X-RateLimit-Remaining`, and `X-RateLimit-Reset`.
  - **HTTP 429:** When a client exceeds their limit, MeterFlow immediately responds with `HTTP 429 Too Many Requests` and a `Retry-After: <seconds>` header.
  - **Resilience Fallback:** If Redis is temporarily unreachable, MeterFlow automatically fails over to high-speed in-memory FakeRedis so rate limiting continues without crashing.

### E. Quota Tracking & Enforcement (`app/services/quota_service.py`)
- **What it does:** Enforces monthly allowances:
  - **Free:** 10,000 requests / month (hard limit)
  - **Pro:** 100,000 requests / month (soft limit, allows paid overages)
  - **Enterprise:** 1,000,000 requests / month
- **How it works:**
  - Evaluates cumulative usage during the current 30-day billing cycle.
  - At **$\ge$ 80% usage**, it injects an `X-Quota-Warning: Near monthly limit` header so customer systems get warned early.
  - At **100% usage** on hard-capped plans, it blocks excess calls with `HTTP 429 Monthly quota exceeded`.

### F. Daily Rollup Aggregator (`app/services/aggregation_service.py`)
- **What it does:** Sums up raw logs into clean daily summaries.
- **Why it matters:** Querying millions of individual raw event rows to calculate bills would be slow and expensive.
- **How it works:** The background rollup worker rolls up raw requests into `usage_daily` tables (grouping by user, subscription, endpoint, and day). It is **strictly idempotent** (`ON CONFLICT DO UPDATE`), meaning it can run repeatedly without creating duplicate records or corrupted totals.

### G. Billing & Invoicing Engine (`app/services/billing_service.py`)
- **What it does:** Calculates usage bills and issues sequential, itemized invoices (`INV-YYYYMM-XXXX`).
- **How it works:**
  - Base monthly fee (e.g. $29.00 for Pro).
  - Calculates tier overages: if a customer uses 5,000 extra requests at $0.01 per 1,000, it computes an overage charge of $0.05.
  - Tracks status progression: `draft` $\rightarrow$ `open` $\rightarrow$ `paid` (or `void`).

### H. Payment Gateway & Webhooks (`app/services/razorpay_service.py` & `payments.py`)
- **What it does:** Connects to Razorpay Test Mode to collect invoice payments online.
- **How it works:**
  - **Precise Currency Math:** Uses Python's `Decimal` type and converts dollar amounts into integer minor units (paise/cents) to prevent floating-point rounding errors.
  - **Order Creation:** Generates a Razorpay payment order for the exact invoice balance.
  - **Signature Verification:** Uses cryptographic HMAC-SHA256 signature verification to ensure payment confirmations cannot be forged.
  - **Webhook Idempotency:** Listens for `payment.captured`, `payment.failed`, and `refund.processed` webhooks. If network retries send the same webhook twice, MeterFlow ignores duplicates and prevents double settlements or accidental payment reversals.

### I. Database Isolation & Testing (`tests/conftest.py`)
- **What it does:** Allows engineers to run tests safely without breaking live customer records.
- **How it works:**
  - Tests run against an isolated database (`neondb_test`), backed by a built-in safety assertion that crashes if tests ever target a non-test database.
  - Each test runs inside an isolated SQL **SAVEPOINT** transaction. Once the test ends, changes are rolled back, leaving zero test clutter.
  - All 61 automated tests pass with 100% success rate.

---

## 3. Database Schema at a Glance

MeterFlow uses 12 relational PostgreSQL tables designed with strict foreign keys, indexing, and check constraints:

| Table Name | Purpose | Key Columns / Constraints |
| :--- | :--- | :--- |
| `users` | Customer & developer accounts | `id (UUID)`, `email (UNIQUE)`, `password_hash`, `status` |
| `subscription_plans`| Catalog pricing tiers | `id`, `name (Free/Pro/Enterprise)`, `price`, `included_requests`, `overage_rate` |
| `subscriptions` | Active tenant subscriptions | `user_id`, `plan_id`, `current_period_start`, `current_period_end`, `status` |
| `api_keys` | Tenant API authentication | `user_id`, `key_prefix`, `key_hash (64-char hex)`, `is_active` |
| `usage_events` | Immutable log of raw API requests | `user_id`, `endpoint`, `status_code`, `latency_ms`, `response_size_bytes` |
| `usage_daily` | Aggregated daily metrics rollup | `user_id`, `date`, `total_requests`, `successful_requests`, `total_latency_ms` |
| `usage_quotas` | Plan quota boundaries | `plan_id`, `metric`, `limit_amount`, `is_hard_limit` |
| `invoices` | Monthly billing statements | `invoice_number`, `user_id`, `amount_due`, `status (open/paid/void)` |
| `invoice_items` | Itemized line items on invoices | `invoice_id`, `description`, `quantity`, `unit_price`, `total_amount` |
| `payments` | Recorded payment transactions | `invoice_id`, `razorpay_order_id`, `razorpay_payment_id`, `amount`, `status` |
| `payment_webhook_events` | Webhook idempotency tracker | `event_id (UNIQUE)`, `event_type`, `processed_at`, `payload` |
| `audit_logs` | Security & compliance audit trail | `actor_id`, `action`, `resource_type`, `resource_id`, `created_at` |

---

## 4. How to Run the Project (Step-by-Step Guide)

### Prerequisites
- **Operating System:** Windows 10/11, macOS, or Linux
- **Python:** Python 3.12 or 3.13 installed
- **Git** (optional)

---

### Step 1: Open Terminal & Activate the Virtual Environment

Open your terminal (PowerShell or Command Prompt on Windows) in the project directory (`D:\Dhruv`):

```powershell
cd D:\Dhruv
```

If the virtual environment is already created:
```powershell
.venv\Scripts\Activate.ps1
```
*(If on Linux/macOS: `source .venv/bin/activate`)*

*(If setting up fresh for the first time:)*
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

---

### Step 2: Verify Configuration (`.env`)
MeterFlow loads its settings automatically from `.env`. Ensure your `.env` contains:
```env
DATABASE_URL=postgresql+psycopg://neondb_owner:npg_gY5j0XqMvNhk@ep-proud-glade-azxwzkfy-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
REDIS_URL=redis://localhost:6379/0
JWT_SECRET_KEY=meterflow-production-super-secret-jwt-key-minimum-32-bytes!
RAZORPAY_KEY_ID=rzp_test_placeholder_key_id
RAZORPAY_KEY_SECRET=rzp_test_placeholder_secret
RAZORPAY_WEBHOOK_SECRET=meterflow_test_webhook_secret_key_12345
ENABLE_HSTS=False
```
*(Note: If local Redis is not running, MeterFlow automatically uses FakeRedis without any manual intervention.)*

---

### Step 3: Start the Backend Server

You have three convenient ways to start the server:

#### Option A: Quick-start batch file (Easiest on Windows)
Double-click `start.bat` in File Explorer, or run in terminal:
```powershell
.\start.bat
```

#### Option B: Dedicated Python runner
```powershell
.venv\Scripts\python run_server.py
```

#### Option C: Direct Uvicorn command
```powershell
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

When started, you will see:
```text
======================================================================
 Starting MeterFlow v0.1.0
 Host:        http://127.0.0.1:8000
 Swagger UI:  http://127.0.0.1:8000/docs
 ReDoc UI:    http://127.0.0.1:8000/redoc
======================================================================
```

---

### Step 4: Explore the Interactive API Documentation

Open your browser and navigate to:
- **Swagger Interactive UI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
  *(Allows you to test every endpoint directly in the browser with full request/response schemas)*
- **ReDoc UI:** [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check Endpoint:** [http://127.0.0.1:8000/api/v1/health](http://127.0.0.1:8000/api/v1/health)

---

### Step 5: Using the Unified Terminal CLI Tool

MeterFlow includes a rich terminal CLI utility for managing the system without leaving PowerShell:

#### Launch the interactive menu:
```powershell
.\meterflow.bat
# or
.venv\Scripts\python cli.py
```

#### Handy single-command shortcuts:
```powershell
# Check database connectivity and total row counts across all tables
.venv\Scripts\python cli.py status

# List registered tenants, subscriptions, and active API keys
.venv\Scripts\python cli.py users

# List catalog subscription tiers (Free, Pro, Enterprise)
.venv\Scripts\python cli.py plans

# View aggregated usage traffic analytics
.venv\Scripts\python cli.py usage

# Display monthly invoices and payment status
.venv\Scripts\python cli.py billing

# Run the daily usage rollup aggregation worker
.venv\Scripts\python cli.py rollup

# Validate relational database foreign key integrity
.venv\Scripts\python cli.py validate
```

---

### Step 6: Running the Full Automated Test Suite

MeterFlow features 61 automated tests covering authentication, API key generation, rate limiting, billing calculations, payment orders, webhook signatures, and security headers.

To execute all tests safely against the isolated test database:
```powershell
.venv\Scripts\python -m pytest tests -v
```

To run a specific test suite:
```powershell
# Run the 13-stage customer lifecycle end-to-end test:
.venv\Scripts\python -m pytest tests/test_e2e_lifecycle.py -v

# Run security hardening tests (headers & IP rate limiting):
.venv\Scripts\python -m pytest tests/test_security_hardening.py -v

# Run payment and webhook tests:
.venv\Scripts\python -m pytest tests/test_payments.py tests/test_payment_webhooks.py -v
```

---

## 5. Quick Hands-On Walkthrough (Testing via PowerShell)

Here is how to test the complete user journey in PowerShell with `curl.exe` or `Invoke-RestMethod`:

### 1. Check System Health
```powershell
curl.exe -s http://127.0.0.1:8000/api/v1/health
```

### 2. Register a New Tenant Account
```powershell
$regBody = @{
    email = "mydeveloper@company.com"
    password = "SuperPassword123!"
    display_name = "My Test Company"
} | ConvertTo-Json

$registerResp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/register" -Method Post -ContentType "application/json" -Body $regBody
$registerResp
```

### 3. Log In & Obtain JWT Bearer Token
```powershell
$loginBody = @{
    email = "mydeveloper@company.com"
    password = "SuperPassword123!"
} | ConvertTo-Json

$loginResp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Method Post -ContentType "application/json" -Body $loginBody
$token = $loginResp.access_token
Write-Host "Obtained JWT Token: Bearer $token"
```

### 4. Generate an API Key
```powershell
$headers = @{ Authorization = "Bearer $token" }
$keyBody = @{ name = "Production Backend Key" } | ConvertTo-Json

$keyResp = Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/api-keys" -Method Post -Headers $headers -ContentType "application/json" -Body $keyBody
$apiKey = $keyResp.raw_key
Write-Host "Generated API Key: $apiKey"
```

### 5. Send Traffic Through the API Gateway (Protected by X-API-Key)
```powershell
$gatewayHeaders = @{ "X-API-Key" = $apiKey }
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/gateway/verify" -Headers $gatewayHeaders
```

### 6. View Real-Time Usage Preview
```powershell
Invoke-RestMethod -Uri "http://127.0.0.1:8000/api/v1/billing/preview" -Headers $headers
```

---

## 6. Project Directory Reference

```
D:\Dhruv\
├── app/                           # Core Application Source Code
│   ├── api/                       # API Route Endpoints
│   │   └── routes/                # auth, api_keys, users, plans, usage, billing, payments
│   ├── core/                      # Core configuration, database engine, security & redis
│   ├── middleware/                # Rate limiters, security headers, gateway verification
│   ├── models/                    # SQLAlchemy 2.0 ORM data models (12 tables)
│   ├── schemas/                   # Pydantic v2 validation and serialization schemas
│   ├── services/                  # Business logic (rate limiting, billing, Razorpay, etc.)
│   └── main.py                    # FastAPI application initialization & routing
├── data/                          # Datasets and Automated Reports
│   ├── processed/                 # Cleaned API usage event CSV datasets
│   ├── raw/                       # Raw web server logs
│   └── reports/                   # Automated JSON test and readiness reports
├── docs/                          # Architecture Guides, ER Diagrams & Completion Reports
├── scripts/                       # Migration, database seeding & diagnostic scripts
├── tests/                         # Pytest automated test suites (61 passing tests)
│   ├── conftest.py                # Isolated test database fixture with SAVEPOINT rollback
│   ├── test_e2e_lifecycle.py      # Complete 13-stage customer journey end-to-end test
│   └── test_security_hardening.py # OWASP headers & auth IP rate limiting tests
├── cli.py                         # Interactive Terminal CLI tool
├── meterflow.bat                  # Shortcut to launch CLI from Windows terminal
├── run_server.py                  # Server launcher script
├── start.bat                      # 1-click Windows server startup file
├── requirements.txt               # Python package dependencies
└── README.md                      # Quick-reference overview
```

---

## 7. Summary & Current Status

- **Phases 1–6 & Step 18:** 100% complete and fully verified.
- **Automated Tests:** 61 out of 61 tests passing (100% pass rate).
- **Code Health:** Pure Python backend, clean layered architecture, bank-grade credential security, zero plain-text secrets, and zero test contamination of development data.
