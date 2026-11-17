"""
Authentication Service
----------------------
Coordinates user registration, login authentication, Bcrypt verification,
and JWT token generation.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import Tuple, Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.security import hash_password, verify_password, create_access_token
from app.core.exceptions import (
    EntityConflictError,
    EntityNotFoundError,
    AuthenticationError,
)
from app.models.user import User
from app.models.subscription import Subscription
from app.models.plan import SubscriptionPlan
from app.repositories.user_repository import UserRepository
from app.schemas.auth import RegisterRequest, LoginRequest


class AuthService:
    def __init__(self, db: Session):
        self.db = db
        self.user_repo = UserRepository(db)

    def register(self, req: RegisterRequest) -> Tuple[User, str, int]:
        """
        Registers a new developer user:
        1. Checks for duplicate email.
        2. Hashes password using bcrypt.
        3. Persists user record.
        4. Links a default 'free' subscription tier if available.
        5. Issues initial JWT access token.
        """
        existing = self.user_repo.get_user_by_email(req.email)
        if existing:
            raise EntityConflictError(f"A user with email '{req.email}' already exists.")

        pwd_hash = hash_password(req.password)
        user = self.user_repo.create_user(
            email=req.email,
            password_hash=pwd_hash,
            display_name=req.display_name,
            status="active",
        )

        # Automatically assign free plan if available
        free_plan = self.db.scalars(
            select(SubscriptionPlan).where(SubscriptionPlan.code == "free")
        ).first()
        if free_plan:
            now = datetime.now(timezone.utc)
            sub = Subscription(
                user_id=user.id,
                plan_id=free_plan.id,
                status="active",
                starts_at=now,
                current_period_start=now,
                current_period_end=now + timedelta(days=365),
                cancel_at_period_end=False,
            )
            self.db.add(sub)

        self.db.commit()
        self.db.refresh(user)

        # Issue JWT
        token, expires_in = create_access_token(
            subject=str(user.id),
            claims={"email": user.email, "name": user.display_name},
        )
        return user, token, expires_in

    def login(self, req: LoginRequest) -> Tuple[User, str, int]:
        """
        Authenticates user credentials:
        1. Looks up user by lowercase email.
        2. Verifies status is 'active'.
        3. Verifies password against stored bcrypt hash.
        4. Issues signed JWT access token.
        """
        user = self.user_repo.get_user_by_email(req.email)
        if not user or user.status != "active":
            raise AuthenticationError("Invalid email or password.")

        if not verify_password(req.password, user.password_hash):
            raise AuthenticationError("Invalid email or password.")

        token, expires_in = create_access_token(
            subject=str(user.id),
            claims={"email": user.email, "name": user.display_name},
        )
        return user, token, expires_in

    def get_user_profile(self, user_id: uuid.UUID) -> User:
        """
        Retrieves complete user profile with eager loaded API keys and subscriptions.
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            raise EntityNotFoundError("User", user_id)
        return user
