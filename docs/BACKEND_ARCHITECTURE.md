# MeterFlow — Backend Architecture Guide

This document explains the software architecture, design principles, and request lifecycle for MeterFlow.

---

## 1. High-Level Architectural Flow

MeterFlow adheres to a strict layered architecture with clear separation of concerns:

```
[ Client: Browser / Mobile App / Postman / SDK ]
                       │
                       ▼  HTTP Request (e.g. GET /api/v1/users/123)
              ┌─────────────────┐
              │  FastAPI Router │ (app/api/routes/)
              └────────┬────────┘
                       │ Validates input types & query schemas
                       ▼
              ┌─────────────────┐
              │   Middleware    │ (app/middleware/request_logging.py)
              └────────┬────────┘ Logs timing, status & attaches X-Process-Time
                       │
                       ▼
              ┌─────────────────┐
              │  Service Layer  │ (app/services/)
              └────────┬────────┘ Implements business rules & entity validation
                       │
                       ▼
              ┌─────────────────┐
              │ Repository Layer│ (app/repositories/)
              └────────┬────────┘ Executes database queries, joins & aggregations
                       │
                       ▼
              ┌─────────────────┐
              │  SQLAlchemy 2.0 │ (app/models/ & app/core/database.py)
              └────────┬────────┘ Object-Relational Mapping & QueuePool connection pool
                       │
                       ▼
              ┌─────────────────┐
              │   PostgreSQL    │ (Cloud / Neon / Local)
              └─────────────────┘
```

---

## 2. Responsibilities of Each Layer

### A. FastAPI Router (`app/api/routes/`)
* **Role:** HTTP Interface controller.
* **Responsibilities:**
  - Defines URL endpoints, HTTP verbs (`GET`, `POST`, etc.), and response status codes.
  - Injects dependencies (database sessions, pagination parameters, services).
  - Serializes domain outputs into clean Pydantic response models.
  - **Does NOT** write SQL queries or calculate metrics directly.

### B. Middleware Layer (`app/middleware/`)
* **Role:** Cross-cutting concerns.
* **Responsibilities:**
  - Request logging (method, path, client address).
  - Execution profiling (calculating request latency and appending `X-Process-Time`).
  - CORS security header injection.

### C. Service Layer (`app/services/`)
* **Role:** Business logic and domain orchestration.
* **Responsibilities:**
  - Implements business logic (e.g., verifying user status, shaping user detail DTOs).
  - Sanitizes sensitive credentials (ensuring password hashes and API key secret hashes are never passed to routers).
  - Raises domain-specific exceptions (`EntityNotFoundError`, `EntityConflictError`).

### D. Repository Layer (`app/repositories/`)
* **Role:** Data access abstraction.
* **Responsibilities:**
  - Executes SQLAlchemy 2.0 queries, filters, and aggregations.
  - Prevents N+1 query problems by using eager loading (`selectinload` / `joinedload`).
  - Keeps SQL query constructs isolated so services remain database-agnostic.

### E. ORM Models (`app/models/`)
* **Role:** Database entity definitions.
* **Responsibilities:**
  - Maps PostgreSQL tables (`users`, `api_keys`, `subscription_plans`, `subscriptions`, `usage_events`) to Python classes.
  - Defines relationships (`relationship(...)`), primary keys, and cascade constraints.

---

## 3. SOLID Principles in MeterFlow

1. **Single Responsibility Principle (SRP):**  
   The Router handles HTTP requests; the Service handles business rules; the Repository handles database operations.
2. **Open/Closed Principle (OCP):**  
   New endpoints or filters can be added without modifying existing core data models.
3. **Liskov Substitution Principle (LSP):**  
   The application communicates with standard SQLAlchemy `Session` interfaces, allowing easy switching between cloud PostgreSQL and isolated test databases.
4. **Interface Segregation Principle (ISP):**  
   Pydantic schemas (`UserResponse`, `UserDetailResponse`, `APIKeyInfo`) separate public data from sensitive credentials.
5. **Dependency Inversion Principle (DIP):**  
   FastAPI routes depend on abstractions (`Depends(get_user_service)`), allowing seamless mocking in tests.
