"""
User Repository
---------------
Encapsulates database access for users, avoiding N+1 queries via eager loading.
"""

import uuid
from typing import Optional, List, Tuple
from sqlalchemy import select, func
from sqlalchemy.orm import Session, selectinload, joinedload

from app.models.user import User
from app.models.subscription import Subscription


class UserRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_users(self, offset: int = 0, limit: int = 20) -> Tuple[List[User], int]:
        """
        Retrieves a paginated list of users and the total count.
        """
        total = self.db.scalar(select(func.count(User.id))) or 0
        stmt = (
            select(User)
            .order_by(User.created_at.desc())
            .offset(offset)
            .limit(limit)
        )
        users = list(self.db.scalars(stmt).all())
        return users, total

    def get_user_by_id(self, user_id: uuid.UUID) -> Optional[User]:
        """
        Retrieves a single user by UUID with API keys and active subscriptions eager loaded.
        Uses selectinload to completely eliminate N+1 query overhead.
        """
        stmt = (
            select(User)
            .options(
                selectinload(User.api_keys),
                selectinload(User.subscriptions).joinedload(Subscription.plan),
            )
            .where(User.id == user_id)
        )
        return self.db.scalars(stmt).first()

    def get_user_by_email(self, email: str) -> Optional[User]:
        stmt = select(User).where(User.email == email.lower())
        return self.db.scalars(stmt).first()

    def create_user(
        self,
        email: str,
        password_hash: str,
        display_name: str,
        status: str = "active",
    ) -> User:
        """
        Creates a new user record in PostgreSQL.
        Enforces lowercase email to satisfy the database check constraint:
        CHECK (email <> '' AND email = LOWER(email))
        """
        user = User(
            email=email.strip().lower(),
            password_hash=password_hash,
            display_name=display_name.strip(),
            status=status,
        )
        self.db.add(user)
        self.db.flush()
        return user
