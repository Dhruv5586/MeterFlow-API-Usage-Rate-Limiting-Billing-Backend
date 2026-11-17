# MeterFlow — Phase 2 Setup & Execution Guide

This guide walks you through setting up and running the MeterFlow Python FastAPI backend locally.

---

## 1. Prerequisites
- **Python 3.12+** (Verified on Python 3.13)
- **PostgreSQL 14+** (Using Neon Cloud or Local instance)
- PowerShell (Windows) or Bash (macOS/Linux)

---

## 2. Environment Setup

### A. Activate the Virtual Environment
On Windows PowerShell:
```powershell
.venv\Scripts\Activate.ps1
```

### B. Verify `.env` Configuration
Ensure your `.env` file exists in the project root (`D:\Dhruv\.env`):
```ini
DATABASE_URL=postgresql://neondb_owner:npg_RWpM9aTXf0Cr@ep-proud-glade-azxwzkfy-pooler.c-3.ap-southeast-1.aws.neon.tech/neondb?sslmode=require
HOST=127.0.0.1
PORT=8000
ENVIRONMENT=development
LOG_LEVEL=info
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

---

## 3. Starting the FastAPI Server

Run the development server with live reload:
```powershell
.venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Once started:
- API Server: **`http://127.0.0.1:8000`**
- Interactive Swagger UI: **`http://127.0.0.1:8000/docs`**
- ReDoc UI: **`http://127.0.0.1:8000/redoc`**

---

## 4. Running the Automated Test Suite

Run all unit, integration, and endpoint tests:
```powershell
.venv\Scripts\python -m pytest tests -v
```

---

## 5. Postman Collection
Import the collection located at:
[`postman/MeterFlow-Phase-2.postman_collection.json`](file:///D:/Dhruv/postman/MeterFlow-Phase-2.postman_collection.json)

Set the collection variable:
- `BASE_URL`: `http://127.0.0.1:8000`
- `DEMO_USER_ID`: `20000000-0000-4000-8000-000000000001`
