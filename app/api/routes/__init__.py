"""Routes module barrel"""
from app.api.routes.health import router as health_router
from app.api.routes.users import router as users_router
from app.api.routes.plans import router as plans_router
from app.api.routes.usage import router as usage_router
from app.api.routes.auth import router as auth_router
from app.api.routes.api_keys import router as api_keys_router
from app.api.routes.gateway import router as gateway_router
from app.api.routes.billing import router as billing_router
from app.api.routes.payments import router as payments_router

__all__ = [
    "health_router",
    "users_router",
    "plans_router",
    "usage_router",
    "auth_router",
    "api_keys_router",
    "gateway_router",
    "billing_router",
    "payments_router",
]
