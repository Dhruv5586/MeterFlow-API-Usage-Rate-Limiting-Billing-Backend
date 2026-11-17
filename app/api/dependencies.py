"""
FastAPI Route Dependencies
--------------------------
Dependency injection providers for database sessions, services, authentication,
and query filters.
"""

import uuid
from typing import Optional, Tuple
from fastapi import Depends, Query, Header, Security, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import decode_access_token
from app.core.exceptions import AuthenticationError, InvalidAPIKeyError
from app.models.user import User
from app.models.api_key import APIKey
from app.services.user_service import UserService
from app.services.plan_service import PlanService
from app.services.usage_service import UsageService
from app.services.auth_service import AuthService
from app.services.api_key_service import APIKeyService
from app.services.billing_service import BillingService
from app.services.aggregation_service import AggregationService
from app.services.payment_service import PaymentService
from app.schemas.common import PaginationParams

# HTTP Bearer scheme for JWT authentication
security_bearer = HTTPBearer(auto_error=False)


def get_user_service(db: Session = Depends(get_db)) -> UserService:
    return UserService(db)


def get_plan_service(db: Session = Depends(get_db)) -> PlanService:
    return PlanService(db)


def get_usage_service(db: Session = Depends(get_db)) -> UsageService:
    return UsageService(db)


def get_auth_service(db: Session = Depends(get_db)) -> AuthService:
    return AuthService(db)


def get_api_key_service(db: Session = Depends(get_db)) -> APIKeyService:
    return APIKeyService(db)


def get_billing_service(db: Session = Depends(get_db)) -> BillingService:
    return BillingService(db)


def get_aggregation_service(db: Session = Depends(get_db)) -> AggregationService:
    return AggregationService(db)


def get_payment_service(db: Session = Depends(get_db)) -> PaymentService:
    return PaymentService(db)


def get_pagination(
    page: int = Query(default=1, ge=1, description="Page number (starts at 1)"),
    size: int = Query(default=20, ge=1, le=100, description="Items per page (1-100)"),
) -> PaginationParams:
    return PaginationParams(page=page, size=size)


def get_current_user(
    auth_credentials: Optional[HTTPAuthorizationCredentials] = Security(security_bearer),
    auth_service: AuthService = Depends(get_auth_service),
) -> User:
    """
    Extracts and validates the JWT Bearer token from the Authorization header.
    Returns the authenticated User ORM model with eager loaded relations.
    """
    if not auth_credentials or not auth_credentials.credentials:
        raise AuthenticationError("Authorization header with Bearer token is required.")

    token = auth_credentials.credentials
    payload = decode_access_token(token)

    sub = payload.get("sub")
    if not sub:
        raise AuthenticationError("Invalid token payload: missing subject identifier.")

    try:
        user_uuid = uuid.UUID(sub)
    except (ValueError, TypeError):
        raise AuthenticationError("Invalid user identifier in token subject.")

    user = auth_service.get_user_profile(user_uuid)
    if user.status != "active":
        raise AuthenticationError("User account is inactive or suspended.")

    return user


def verify_api_key(
    x_api_key: Optional[str] = Header(default=None, alias="X-API-Key", description="Developer secret API Key"),
    api_key_service: APIKeyService = Depends(get_api_key_service),
) -> Tuple[APIKey, User]:
    """
    Validates the X-API-Key header against stored SHA-256 hashes in PostgreSQL.
    Returns:
        (APIKey, User) tuple for authorized requests.
    """
    if not x_api_key:
        raise InvalidAPIKeyError("Missing required 'X-API-Key' authentication header.")

    return api_key_service.authenticate_key(x_api_key)
