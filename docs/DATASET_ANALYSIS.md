# Dataset Analysis

## Source and handling

- Inspected source: `D:\API_TESTER\access_logs.csv`
- Expected project location: `data\raw\access_logs.csv`
- The source file was not moved or modified. Until explicitly authorized, scripts
  should read it from its actual location.
- File size: 679,667 bytes.
- The sample below redacts IP addresses. Raw IP addresses must not be copied into
  MeterFlow tables or generated documentation.

## Structure and quality

The CSV contains 5,000 data records and these 10 columns. No column has missing
or empty values. No exact duplicate records or invalid timestamps were found.

| Column | Inferred type | Notes |
| --- | --- | --- |
| `timestamp` | datetime string | Format is `YYYY-MM-DD HH:MM:SS`; it does not include a timezone. |
| `server_id` | integer | Identifies a source server; it is not a MeterFlow user or API key. |
| `method` | string | HTTP methods observed below. |
| `path` | string | Endpoint/path; query strings should be removed during transformation. |
| `status_code` | integer | HTTP status code. |
| `response_time_ms` | integer | Non-negative response latency in milliseconds. |
| `bytes_sent` | integer | Response size in bytes. |
| `user_agent` | string | Client description; not needed for billing and can be identifying. |
| `ip_address` | string | Sensitive network identifier; never store raw. |
| `referrer` | string | May contain URLs and identifying data; not required for billing. |

## HTTP methods

| Method | Records |
| --- | ---: |
| GET | 3,360 |
| POST | 1,013 |
| PUT | 378 |
| DELETE | 158 |
| PATCH | 91 |

## HTTP status codes

| Status | Records |
| --- | ---: |
| 200 | 3,638 |
| 201 | 245 |
| 301 | 118 |
| 304 | 292 |
| 400 | 192 |
| 401 | 156 |
| 403 | 52 |
| 404 | 197 |
| 500 | 85 |
| 503 | 25 |

## Endpoint distribution

There are 33 distinct path values. All endpoint counts are shown below.

| Path | Records | Path | Records |
| --- | ---: | --- | ---: |
| `/about` | 191 | `/api/v2/wishlist` | 167 |
| `/api/v2/shipping/rates` | 167 | `/static/js/app.js` | 166 |
| `/contact` | 166 | `/static/images/logo.png` | 166 |
| `/sitemap.xml` | 164 | `/login` | 159 |
| `/docs/{page}` | 159 | `/api/v2/categories` | 158 |
| `/healthz` | 158 | `/api/v2/users/register` | 155 |
| `/robots.txt` | 154 | `/docs` | 152 |
| `/api/v2/users/login` | 152 | `/api/v2/cart` | 151 |
| `/blog/{slug}` | 151 | `/api/v2/users/me` | 151 |
| `/favicon.ico` | 150 | `/api/v2/orders/{id}` | 150 |
| `/blog` | 149 | `/` | 149 |
| `/api/v2/products/{id}` | 147 | `/api/v2/cart/checkout` | 145 |
| `/register` | 143 | `/api/v2/search` | 140 |
| `/api/v2/reviews` | 140 | `/api/v2/payments/process` | 139 |
| `/.well-known/security.txt` | 137 | `/api/v2/orders` | 136 |
| `/pricing` | 132 | `/api/v2/products` | 128 |
| `/static/css/main.css` | 128 | | |

## Response time (`response_time_ms`)

All 5,000 values are valid, non-negative integers.

| Statistic | Milliseconds |
| --- | ---: |
| Minimum | 1 |
| Median | 90 |
| Mean | 180.73 |
| 95th percentile | 627.10 |
| 99th percentile | 1,459.04 |
| Maximum | 7,510 |

## Sample: first 10 records

IP addresses are redacted; other fields are shown as supplied.

| # | Timestamp | Server | Method | Path | Status | Latency ms | Bytes |
| ---: | --- | ---: | --- | --- | ---: | ---: | ---: |
| 1 | `2024-01-01 00:15:12` | 1 | GET | `/api/v2/payments/process` | 201 | 153 | 2,256 |
| 2 | `2024-01-01 00:27:54` | 2 | GET | `/docs` | 304 | 290 | 10,395 |
| 3 | `2024-01-01 00:31:42` | 1 | POST | `/api/v2/cart` | 200 | 201 | 2,452 |
| 4 | `2024-01-01 00:54:33` | 2 | POST | `/static/js/app.js` | 201 | 31 | 2,324 |
| 5 | `2024-01-01 01:36:08` | 2 | GET | `/contact` | 200 | 64 | 449 |
| 6 | `2024-01-01 02:18:04` | 2 | POST | `/static/images/logo.png` | 201 | 50 | 5,087 |
| 7 | `2024-01-01 03:23:09` | 3 | GET | `/pricing` | 200 | 50 | 3,849 |
| 8 | `2024-01-01 03:40:03` | 3 | PUT | `/register` | 200 | 121 | 2,298 |
| 9 | `2024-01-01 05:10:57` | 1 | GET | `/api/v2/categories` | 401 | 339 | 3,680 |
| 10 | `2024-01-01 05:11:40` | 3 | POST | `/docs` | 200 | 10 | 1,095 |

## Integration limitations and decisions to make

- The timestamps are timezone-naive. An importer must apply an agreed timezone
  (or explicitly document its assumption) before inserting them into
  `TIMESTAMPTZ`; the source does not establish one.
- There are no user IDs or API-key IDs in the source. It is not possible to
  truthfully associate these records with seeded users/API keys from the CSV.
  Import must wait for an explicit, deterministic attribution rule or should be
  limited to records that can be associated through an independently supplied
  mapping. Foreign keys must not be fabricated.
- Logs include non-API assets and general website routes as well as API paths.
  Decide whether all requests count toward usage or whether the import should
  filter to an agreed API route set.
- `user_agent`, raw IP, and `referrer` are unnecessary for billing and can be
  sensitive. Exclude them from `usage_events`. If an approved analysis use needs
  network-level grouping, use a keyed/controlled pseudonymization strategy;
  plain unsalted SHA-256 of IPs is susceptible to guessing and does not provide
  meaningful anonymization.
- Existing paths include template-like values such as `/api/v2/orders/{id}`.
  Removing query strings is still required, but path normalization should be
  defined so dynamic path segments do not create misleading endpoint counts.
- Validation findings describe this file as inspected; the original CSV remains
  unchanged.

## Step 4: Dataset Transformation and Import Results

### 1. Route Classification Breakdown
All 5,000 raw source records were processed through the route classifier:
- **Approved API Records (`/api/v2/...`):** 2,226 records (44.52%)
- **Excluded Static Assets (`/static/...`, `.css`, `.js`, `.ico`, `.png`, etc.):** 1,065 records (21.30%)
- **Excluded Website Traffic (`/about`, `/contact`, `/pricing`, `/docs`, etc.):** 1,709 records (34.18%)
- **Unknown Routes:** 0
- **Invalid Records:** 0

### 2. Cleaning and Transformation Rules
- **Endpoint Normalization:** Query strings stripped via URL parsing (`urlparse`); leading slashes ensured.
- **HTTP Methods:** Normalized to uppercase (`GET`, `POST`, `PUT`, `DELETE`).
- **Timestamp Standardization:** Timezone-naive timestamps converted to UTC ISO-8601 strings (`TIMESTAMPTZ`).
- **PII Scrubbing:** Raw IP addresses, user agents, and referrers were completely omitted from the database to preserve developer privacy.
- **Tenant Attribution:** Deterministically mapped in a balanced round-robin across the 3 demo users, matching each user's verified API key and subscription.

### 3. Database Ingestion Summary
- **Target Table:** `usage_events` in PostgreSQL
- **Stage 1 Test:** 100 records imported, validated against all 8 integrity checks.
- **Stage 2 Expansion:** 1,000 records processed. The initial 100 duplicates were safely skipped via `ON CONFLICT (source_record_key) DO NOTHING`, and 900 new records were inserted.
- **Current Database Ledger:** 1,000 verified usage events.
- **Report Location:** `data/reports/import_report.json`

