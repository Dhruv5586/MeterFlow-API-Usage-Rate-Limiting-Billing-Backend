"""
User Service
------------
Business logic for user operations.
"""

import uuid
from typing import List, Tuple
from sqlalchemy.orm import Session

from app.repositories.user_repository import UserRepository
from app.models.user import User
from app.core.exceptions import EntityNotFoundError
from app.schemas.user import UserDetailResponse, APIKeyInfo, SubscriptionInfo


class UserService:
    def __init__(self, db: Session):
        self.repo = UserRepository(db)

    def list_users(self, offset: int, limit: int) -> Tuple[List[User], int]:
        return self.repo.get_users(offset=offset, limit=limit)

    def get_user_detail(self, user_id: uuid.UUID) -> UserDetailResponse:
        user = self.repo.get_user_by_id(user_id)
        if not user:
            raise EntityNotFoundError(entity_name="User", entity_id=user_id)

        # Build clean DTO safely excluding secret hashes
        api_keys_dto = [
            APIKeyInfo(
                id=k.id,
                name=k.name,
                key_prefix=k.key_prefix,
                created_at=k.created_at,
                expires_at=k.expires_at,
                last_used_at=k.last_used_at,
            )
            for k in user.api_keys
        ]

        subs_dto = [
            SubscriptionInfo(
                id=s.id,
                plan_id=s.plan_id,
                plan_code=s.plan.code if s.plan else None,
                plan_name=s.plan.name if s.plan else None,
                status=s.status,
                current_period_start=s.current_period_start,
                current_period_end=s.current_period_end,
            )
            for s in user.subscriptions
        ]

        return UserDetailResponse(
            id=user.id,
            email=user.email,
            display_name=user.display_name,
            status=user.status,
            created_at=user.created_at,
            updated_at=user.updated_at,
            api_keys=api_keys_dto,
            subscriptions=subs_dto,
        )
