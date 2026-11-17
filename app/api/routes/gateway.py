"""
API Gateway Verification Routes
-------------------------------
Endpoints representing downstream APIs protected by API Gateway X-API-Key authentication.
"""

from fastapi import APIRouter, Request, status, Depends
from app.api.dependencies import verify_api_key

router = APIRouter(prefix="/gateway", tags=["API Gateway"])


@router.get(
    "/verify",
    status_code=status.HTTP_200_OK,
    summary="Verify API Key and test Gateway authorization",
    description="Validates the X-API-Key header through API Gateway middleware and returns the authenticated key and tenant metadata.",
)
def verify_gateway_key(request: Request):
    api_key = getattr(request.state, "api_key", None)
    user = getattr(request.state, "user", None)
    rate_result = getattr(request.state, "rate_result", None)

    return {
        "status": "authorized",
        "message": "API key successfully verified by MeterFlow API Gateway.",
        "key_id": str(api_key.id) if api_key else None,
        "key_name": api_key.name if api_key else None,
        "key_prefix": api_key.key_prefix if api_key else None,
        "user_id": str(user.id) if user else None,
        "user_email": user.email if user else None,
        "user_display_name": user.display_name if user else None,
        "rate_limit": {
            "limit": rate_result.limit if rate_result else None,
            "remaining": rate_result.remaining if rate_result else None,
            "reset_seconds": rate_result.reset_seconds if rate_result else None,
        } if rate_result else None,
    }


@router.get(
    "/echo",
    status_code=status.HTTP_200_OK,
    summary="Gateway Echo Service",
    description="Sample downstream microservice protected by API Gateway rate limiting and quota verification.",
)
def gateway_echo(request: Request):
    api_key = getattr(request.state, "api_key", None)
    user = getattr(request.state, "user", None)
    return {
        "service": "downstream-echo",
        "timestamp": request.headers.get("date"),
        "caller": user.email if user else "unknown",
        "key_prefix": api_key.key_prefix if api_key else "unknown",
    }
