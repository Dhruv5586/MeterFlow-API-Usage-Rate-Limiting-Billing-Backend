# MeterFlow — API Usage, Rate Limiting & Billing Management System

MeterFlow is an enterprise-grade backend infrastructure engine designed for API metering, tenant quota tracking, subscription billing, and real-time usage analytics.

Built with **Python 3.13**, **FastAPI**, **SQLAlchemy 2.0**, **PostgreSQL 16**, and **Pydantic v2**.

---

## Architecture Overview

```
Client (HTTP/Postman/SDK)
          │
          ▼
   FastAPI Router (app/api/routes/)
          │
          ▼
   Request Logging & Timing Middleware (app/middleware/)
          │
          ▼
   Service Layer (app/services/)
          │
          ▼
   Repository Layer (app/repositories/)
          │
          ▼
   SQLAlchemy 2.0 ORM (app/models/)
          │
          ▼
   PostgreSQL Database (Neon Cloud / Local)
```

---

## Features (Phase 1 & Phase 2 Complete)

- **PostgreSQL 16 Database Architecture:** 10 normalized production tables (`users`, `api_keys`, `subscription_plans`, `subscriptions`, `usage_events`, `usage_daily`, `usage_quotas`, `invoices`, `invoice_items`, `audit_logs`).
- **Bank-Grade Security:** API keys generated via CSPRNG (`secrets.token_urlsafe`) and stored as 64-character lowercase SHA-256 hashes. Plaintext keys are never persisted.
- **FastAPI Read-Only Endpoints:**
  - `GET /api/v1/health`: System health and live database connection status.
  - `GET /api/v1/users`: Paginated developer accounts (credentials excluded).
  - `GET /api/v1/users/{user_id}`: Full developer account detail with active plans and API key prefixes.
  - `GET /api/v1/plans`: Catalog pricing tiers (Free, Pro, Enterprise).
  - `GET /api/v1/usage/summary`: Aggregated API usage metrics (total, success, failed, average latency, bytes).
  - `GET /api/v1/usage/events`: Paginated real-time access events log.
- **High-Performance Ingestion:** Transformed 5,000 raw access logs; ingested 1,000 verified API events with `ON CONFLICT (source_record_key) DO NOTHING` idempotency.
- **Sub-Millisecond Querying:** Optimized composite indexes support sub-0.2ms EXPLAIN ANALYZE queries.

---

## Quickstart

### 1. Setup Virtual Environment
```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy `.env.example` to `.env` and provide your PostgreSQL connection string:
```ini
DATABASE_URL=postgresql://<user>:<password>@<host>/<dbname>?sslmode=require
```

### 3. Start the Server
```powershell
.venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```
- Interactive Swagger UI: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- ReDoc: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

### 4. Run Automated Tests
```powershell
.venv\Scripts\python -m pytest tests -v
```

---

## Documentation Links
- [Backend Architecture Guide](docs/BACKEND_ARCHITECTURE.md)
- [API Endpoints Documentation](docs/API_DOCUMENTATION.md)
- [Phase 2 Setup Guide](docs/PHASE_2_SETUP.md)
- [Database Design & Normalization](docs/DATABASE_DESIGN.md)
- [Dataset Profiling & Cleaning](docs/DATASET_ANALYSIS.md)
- [Entity-Relationship Diagram](docs/ER_DIAGRAM.md)
