"""
Authentication Routes
---------------------
Endpoints for user registration, user login, and current user profile inspection.
"""

from fastapi import APIRouter, Depends, status
from app.api.dependencies import get_auth_service, get_current_user
from app.services.auth_service import AuthService
from app.models.user import User
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse
from app.schemas.user import UserResponse, UserDetailResponse, APIKeyInfo, SubscriptionInfo

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new developer tenant account",
    description="Creates a new developer account, hashes password using Bcrypt, provisions a default subscription tier, and returns a signed JWT access token.",
)
def register(
    req: RegisterRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    user, token, expires_in = auth_service.register(req)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
    summary="Authenticate developer credentials and obtain JWT access token",
    description="Validates email and password against stored Bcrypt hashes and issues a signed JWT access token.",
)
def login(
    req: LoginRequest,
    auth_service: AuthService = Depends(get_auth_service),
):
    user, token, expires_in = auth_service.login(req)
    return TokenResponse(
        access_token=token,
        token_type="bearer",
        expires_in=expires_in,
        user=UserResponse.model_validate(user),
    )


@router.get(
    "/me",
    response_model=UserDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get current authenticated user profile",
    description="Inspects the Bearer JWT token from the Authorization header and returns full profile details with active subscriptions and API keys.",
)
def get_current_user_profile(
    current_user: User = Depends(get_current_user),
):
    # Map subscriptions with plan codes/names
    sub_infos = []
    for s in current_user.subscriptions:
        sub_infos.append(
            SubscriptionInfo(
                id=s.id,
                plan_id=s.plan_id,
                plan_code=s.plan.code if s.plan else None,
                plan_name=s.plan.name if s.plan else None,
                status=s.status,
                current_period_start=s.current_period_start,
                current_period_end=s.current_period_end,
            )
        )

    # Map API keys (excluding secret hashes)
    key_infos = [
        APIKeyInfo(
            id=k.id,
            name=k.name,
            key_prefix=k.key_prefix,
            created_at=k.created_at,
            expires_at=k.expires_at,
            last_used_at=k.last_used_at,
        )
        for k in current_user.api_keys
    ]

    return UserDetailResponse(
        id=current_user.id,
        email=current_user.email,
        display_name=current_user.display_name,
        status=current_user.status,
        created_at=current_user.created_at,
        updated_at=current_user.updated_at,
        api_keys=key_infos,
        subscriptions=sub_infos,
    )
