"""
API Key Repository
------------------
Data access layer for managing API keys in PostgreSQL.
Encapsulates key generation queries, revocation, and authentication lookups.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional, List
from sqlalchemy import select, update
from sqlalchemy.orm import Session, joinedload

from app.models.api_key import APIKey
from app.models.user import User


class APIKeyRepository:
    def __init__(self, db: Session):
        self.db = db

    def create_api_key(
        self,
        user_id: uuid.UUID,
        name: str,
        key_prefix: str,
        key_hash: str,
        expires_at: Optional[datetime] = None,
    ) -> APIKey:
        """
        Inserts a new API key record.
        Strictly satisfies database constraints:
        - key_hash: CHAR(64) SHA-256 hex digest
        - expires_at: NULL or > created_at
        """
        api_key = APIKey(
            user_id=user_id,
            name=name.strip(),
            key_prefix=key_prefix,
            key_hash=key_hash,
            expires_at=expires_at,
        )
        self.db.add(api_key)
        self.db.flush()
        return api_key

    def get_by_id_and_user(self, key_id: uuid.UUID, user_id: uuid.UUID) -> Optional[APIKey]:
        """
        Retrieves an API key belonging to a specific user.
        """
        stmt = (
            select(APIKey)
            .where(APIKey.id == key_id, APIKey.user_id == user_id)
        )
        return self.db.scalars(stmt).first()

    def get_by_hash(self, key_hash: str) -> Optional[APIKey]:
        """
        Finds an API key by its 64-character SHA-256 hash.
        Eagerly loads the associated User entity for gateway verification.
        """
        stmt = (
            select(APIKey)
            .options(joinedload(APIKey.user))
            .where(APIKey.key_hash == key_hash)
        )
        return self.db.scalars(stmt).first()

    def list_by_user(self, user_id: uuid.UUID) -> List[APIKey]:
        """
        Returns all API keys for a user, ordered with newest first.
        """
        stmt = (
            select(APIKey)
            .where(APIKey.user_id == user_id)
            .order_by(APIKey.created_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def revoke_key(self, key_id: uuid.UUID, user_id: uuid.UUID) -> Optional[APIKey]:
        """
        Sets revoked_at to current UTC timestamp.
        """
        key = self.get_by_id_and_user(key_id=key_id, user_id=user_id)
        if not key:
            return None
        
        if key.revoked_at is None:
            key.revoked_at = datetime.now(timezone.utc)
            self.db.flush()
        return key

    def touch_last_used(self, key_id: uuid.UUID) -> None:
        """
        Updates last_used_at timestamp when a request is authenticated via this key.
        """
        stmt = (
            update(APIKey)
            .where(APIKey.id == key_id)
            .values(last_used_at=datetime.now(timezone.utc))
        )
        self.db.execute(stmt)
