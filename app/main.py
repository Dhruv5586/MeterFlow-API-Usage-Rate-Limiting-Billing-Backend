"""
MeterFlow Main Application
--------------------------
FastAPI application initialization, router aggregation, CORS setup,
centralized exception handling, and request logging.
"""

import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError

from app.core.config import settings
from app.core.database import check_database_health
from app.core.exceptions import (
    MeterFlowException,
    EntityNotFoundError,
    EntityConflictError,
    DatabaseConnectionError,
    InvalidParameterError,
    AuthenticationError,
    AuthorizationError,
    InvalidAPIKeyError,
    RateLimitExceededError,
)
from app.middleware.request_logging import RequestLoggingMiddleware
from app.middleware.api_key_gateway import APIKeyGatewayMiddleware
from app.middleware.security_headers import SecurityHeadersMiddleware
from app.middleware.auth_rate_limit import AuthRateLimitMiddleware
from app.api.routes import (
    health_router,
    users_router,
    plans_router,
    usage_router,
    auth_router,
    api_keys_router,
    gateway_router,
    billing_router,
    payments_router,
)

# Configure logging
logging.basicConfig(
    level=getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("meterflow.app")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application startup and shutdown lifecycle manager.
    Validates database connection on boot.
    """
    logger.info(f"Starting {settings.APP_NAME} v{settings.APP_VERSION} ({settings.ENVIRONMENT})")
    try:
        check_database_health()
        logger.info("[✓] Database connection pool initialized and healthy.")
    except Exception as exc:
        logger.warning(f"[!] Warning: Initial database ping failed on startup: {exc}")
    yield
    logger.info(f"Shutting down {settings.APP_NAME} gracefully.")


# Initialize FastAPI application
app = FastAPI(
    title=settings.APP_NAME,
    description="Backend API Usage, Rate Limiting and Billing Management System",
    version=settings.APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
    lifespan=lifespan,
)

# 1. Configure Middleware Stack
# Middlewares are applied in reverse order of addition (outermost added last)
app.add_middleware(RequestLoggingMiddleware)
app.add_middleware(APIKeyGatewayMiddleware)
app.add_middleware(AuthRateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(SecurityHeadersMiddleware)


# 3. Centralized Exception Handlers
@app.exception_handler(AuthenticationError)
async def authentication_error_handler(request: Request, exc: AuthenticationError):
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        headers={"WWW-Authenticate": "Bearer"},
        content={
            "error": "Unauthorized",
            "message": exc.message,
            "details": exc.details,
            "path": request.url.path,
        },
    )


@app.exception_handler(AuthorizationError)
async def authorization_error_handler(request: Request, exc: AuthorizationError):
    return JSONResponse(
        status_code=status.HTTP_403_FORBIDDEN,
        content={
            "error": "Forbidden",
            "message": exc.message,
            "details": exc.details,
            "path": request.url.path,
        },
    )


@app.exception_handler(RateLimitExceededError)
async def rate_limit_exceeded_handler(request: Request, exc: RateLimitExceededError):
    return JSONResponse(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        headers={
            "Retry-After": str(exc.retry_after),
            "X-RateLimit-Limit": str(exc.limit),
            "X-RateLimit-Remaining": str(exc.remaining),
            "X-RateLimit-Reset": str(exc.reset_seconds),
        },
        content={
            "error": "Too Many Requests",
            "message": exc.message,
            "limit": exc.limit,
            "remaining": exc.remaining,
            "reset_seconds": exc.reset_seconds,
            "path": request.url.path,
        },
    )


@app.exception_handler(EntityNotFoundError)
async def entity_not_found_handler(request: Request, exc: EntityNotFoundError):
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={
            "error": "Not Found",
            "message": exc.message,
            "details": exc.details,
            "path": request.url.path,
        },
    )


@app.exception_handler(InvalidParameterError)
async def invalid_parameter_handler(request: Request, exc: InvalidParameterError):
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={
            "error": "Bad Request",
            "message": exc.message,
            "details": exc.details,
            "path": request.url.path,
        },
    )


@app.exception_handler(EntityConflictError)
async def entity_conflict_handler(request: Request, exc: EntityConflictError):
    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content={
            "error": "Conflict",
            "message": exc.message,
            "details": exc.details,
            "path": request.url.path,
        },
    )


@app.exception_handler(DatabaseConnectionError)
async def db_connection_error_handler(request: Request, exc: DatabaseConnectionError):
    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content={
            "error": "Service Unavailable",
            "message": "Database is temporarily unreachable. Please retry later.",
            "path": request.url.path,
        },
    )


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    formatted_errors = []
    for err in exc.errors():
        formatted_errors.append({
            "field": " -> ".join(str(loc) for loc in err.get("loc", [])),
            "issue": err.get("msg"),
            "type": err.get("type"),
        })
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "error": "Validation Error",
            "message": "One or more request parameters failed validation.",
            "details": formatted_errors,
            "path": request.url.path,
        },
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.error(f"Unhandled exception on {request.method} {request.url.path}: {exc}", exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={
            "error": "Internal Server Error",
            "message": "An unexpected server error occurred.",
            "path": request.url.path,
        },
    )


# 4. Register API Routers under /api/v1
api_v1_prefix = "/api/v1"
app.include_router(health_router, prefix=api_v1_prefix)
app.include_router(auth_router, prefix=api_v1_prefix)
app.include_router(api_keys_router, prefix=api_v1_prefix)
app.include_router(gateway_router, prefix=api_v1_prefix)
app.include_router(users_router, prefix=api_v1_prefix)
app.include_router(plans_router, prefix=api_v1_prefix)
app.include_router(usage_router, prefix=api_v1_prefix)
app.include_router(billing_router, prefix=api_v1_prefix)
app.include_router(payments_router, prefix=api_v1_prefix)


@app.get("/", include_in_schema=False)
def root():
    return {
        "service": settings.APP_NAME,
        "version": settings.APP_VERSION,
        "docs_url": "/docs",
        "health_url": "/api/v1/health",
    }
