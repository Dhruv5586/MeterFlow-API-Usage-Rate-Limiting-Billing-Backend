# 💻 MeterFlow Terminal & CLI Reference Guide

MeterFlow includes a unified command-line tool (`meterflow` or `python cli.py`) designed for working entirely from the terminal (Command Prompt, PowerShell, Windows Terminal, Linux/macOS).

---

## ⚡ Quick Start: Interactive Menu

Open your terminal in `D:\Dhruv` and simply run:

```bash
meterflow
```
*(or `.\meterflow.bat` / `python cli.py`)*


This launches the **MeterFlow Terminal Control Panel**:

```text
  __  __      _            _____ _               
 |  \/  |    | |          |  ___| |              
 | \  / | ___| |_ ___ _ __| |_  | | _____      __
 | |\/| |/ _ \ __/ _ \ '__|  _| | |/ _ \ \ /\ / /
 | |  | |  __/ ||  __/ |  | |   | | (_) \ V  V / 
 |_|  |_|\___|\__\___|_|  \_|   |_|\___/ \_/\_/  
 API Usage, Rate Limiting & Billing Management Engine

MeterFlow Terminal Control Panel
Choose an action by typing its number and pressing Enter:

  [1] Start API Development Server  (Uvicorn on port 8000)
  [2] Check Database & System Status (Table counts, health check)
  [3] View Tenants & API Keys        (Tenants, plans, keys)
  [4] View Subscription Plans        (Quotas, pricing, overage)
  [5] View Live Usage Analytics      (Latency, traffic, breakdown)
  [6] Run Automated Test Suite       (18 Pytest unit/integration tests)
  [7] Run Database Integrity Check   (EXPLAIN ANALYZE & constraint audits)
  [8] Transform Access Logs Dataset  (CSV cleaning & URL normalization)
  [9] Import Events to PostgreSQL    (Batch ingestion with deduplication)
  [0] Exit Terminal
```

---

## 🛠️ Direct Terminal Subcommands

You can also run specific commands directly without the interactive menu:

| Terminal Command | Description |
|------------------|-------------|
| `meterflow server` | Start the FastAPI development server on `http://127.0.0.1:8000` with auto-reload |
| `meterflow server --port 9000` | Start server on custom port |
| `meterflow status` | Ping PostgreSQL database, check health, and count rows in all 10 tables |
| `meterflow users` | Print registered tenants, active subscriptions, and SHA-256 API key prefixes |
| `meterflow plans` | Display all subscription tiers, currency prices, and billing intervals |
| `meterflow usage` | Display traffic summary, tenant breakdown, and ASCII HTTP method distribution |
| `meterflow test` | Execute the 18 Pytest unit and integration tests |
| `meterflow validate` | Run database constraints audit and `EXPLAIN ANALYZE` benchmarks |
| `meterflow transform` | Transform raw `data/raw/access_logs.csv` into `data/processed/api_usage_events.csv` |
| `meterflow import` | Ingest clean API usage events into PostgreSQL with conflict resolution |

---

## 🔍 Examples

### Check Database Health and Table Counts
```powershell
meterflow status
```
**Output:**
```text
[1] Database Connectivity Check
    Connecting to: ep-proud-glade-azxwzkfy-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
    [OK] Status: HEALTHY (PostgreSQL 16 active & responsive)

[2] Database Tables & Record Counts
    Table Name                 Rows   Description
    ---------------------- --------   -----------------------------------
    users                         3   Registered tenant accounts
    api_keys                      3   Tenant API keys (SHA-256 hashed)
    subscription_plans            3   Billing tiers & request quotas
    subscriptions                 3   Active tenant subscriptions
    usage_events               1000   Ingested API usage logs
    ...
```

### Inspect Live API Usage in Terminal
```powershell
meterflow usage
```
**Output:**
```text
  Total Ingested Events : 1,000
  Active Demo Tenants   : 3
  Average Latency       : 193.86 ms (Min: 1.00 ms | Max: 7510.00 ms)
  Total Transferred     : 8.22 MB (8,615,893 bytes)

  Tenant Breakdown:
    * DataBridge Systems        :  344 events | Avg Latency: 201.5ms | Errors: 59
    * TechNova Solutions        :  333 events | Avg Latency: 208.1ms | Errors: 51
    * CloudSphere Technologies  :  323 events | Avg Latency: 171.0ms | Errors: 44

  HTTP Methods Distribution:
    * GET   :  667 ( 66.7%) ################
    * POST  :  196 ( 19.6%) ####
    * PUT   :   86 (  8.6%) ##
    * DELETE:   33 (  3.3%) 
    * PATCH :   18 (  1.8%) 
```

### Run All Automated Tests
```powershell
meterflow test
```

---

## 💡 Aliases & Alternatives

If you prefer different commands, all of the following work identically in PowerShell or CMD:

```powershell
# Option 1: Direct batch shortcut
meterflow status

# Option 2: cli shortcut
cli status

# Option 3: Python module
.venv\Scripts\python cli.py status
```
