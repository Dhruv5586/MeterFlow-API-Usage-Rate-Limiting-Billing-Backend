"""
Users Router
------------
Endpoints for developer accounts.
"""

import uuid
from fastapi import APIRouter, Depends, status, Path
from app.schemas.user import UserResponse, UserDetailResponse
from app.schemas.common import Page, PaginationParams
from app.services.user_service import UserService
from app.api.dependencies import get_user_service, get_pagination

router = APIRouter(prefix="/users", tags=["Users"])


@router.get(
    "",
    response_model=Page[UserResponse],
    status_code=status.HTTP_200_OK,
    summary="List Developer Users (Paginated)",
    description="Returns a paginated list of registered developers. Password hashes are never exposed.",
)
def list_users(
    pagination: PaginationParams = Depends(get_pagination),
    service: UserService = Depends(get_user_service),
) -> Page[UserResponse]:
    users, total = service.list_users(offset=pagination.offset, limit=pagination.size)
    items = [UserResponse.model_validate(u) for u in users]
    return Page.create(items=items, total=total, page=pagination.page, size=pagination.size)


@router.get(
    "/{user_id}",
    response_model=UserDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Developer User Details",
    description="Returns details for a single developer by UUID, including active subscriptions and API key prefixes.",
)
def get_user(
    user_id: uuid.UUID = Path(..., description="Valid user UUID"),
    service: UserService = Depends(get_user_service),
) -> UserDetailResponse:
    return service.get_user_detail(user_id)
