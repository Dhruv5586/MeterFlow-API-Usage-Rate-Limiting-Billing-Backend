"""
API Key Service
---------------
Business logic for generating, listing, revoking, and authenticating API keys.
"""

import uuid
from datetime import datetime, timezone, timedelta
from typing import List, Tuple, Optional
from sqlalchemy.orm import Session

from app.core.security import generate_api_key, hash_api_key
from app.core.exceptions import (
    EntityNotFoundError,
    InvalidAPIKeyError,
    InvalidParameterError,
)
from app.models.api_key import APIKey
from app.models.user import User
from app.repositories.api_key_repository import APIKeyRepository
from app.repositories.user_repository import UserRepository
from app.schemas.api_key import (
    APIKeyCreateRequest,
    APIKeyCreateResponse,
    APIKeyResponse,
    APIKeyRevokeResponse,
)


class APIKeyService:
    def __init__(self, db: Session):
        self.db = db
        self.key_repo = APIKeyRepository(db)
        self.user_repo = UserRepository(db)

    def create_key(self, user_id: uuid.UUID, req: APIKeyCreateRequest) -> APIKeyCreateResponse:
        """
        Generates and stores a new API key for the user.
        Plaintext secret is returned ONLY in the response and is never stored.
        """
        user = self.user_repo.get_user_by_id(user_id)
        if not user:
            raise EntityNotFoundError("User", user_id)

        now = datetime.now(timezone.utc)
        expires_at: Optional[datetime] = None
        if req.expires_in_days is not None:
            expires_at = now + timedelta(days=req.expires_in_days)

        # Generate cryptographic key, prefix, and hash
        full_key, prefix, key_hash = generate_api_key(environment="live")

        created_key = self.key_repo.create_api_key(
            user_id=user_id,
            name=req.name,
            key_prefix=prefix,
            key_hash=key_hash,
            expires_at=expires_at,
        )
        self.db.commit()
        self.db.refresh(created_key)

        return APIKeyCreateResponse(
            id=created_key.id,
            name=created_key.name,
            key_prefix=created_key.key_prefix,
            api_key=full_key,  # Returned only once!
            created_at=created_key.created_at,
            expires_at=created_key.expires_at,
            message="Store this API key safely in your application environment. You will not be able to view it again.",
        )

    def list_keys(self, user_id: uuid.UUID) -> List[APIKeyResponse]:
        """
        Lists all API keys for the user (with active/revoked status, without secret).
        """
        keys = self.key_repo.list_by_user(user_id)
        return [APIKeyResponse.from_orm_model(k) for k in keys]

    def revoke_key(self, key_id: uuid.UUID, user_id: uuid.UUID) -> APIKeyRevokeResponse:
        """
        Revokes an API key belonging to the user.
        """
        revoked = self.key_repo.revoke_key(key_id=key_id, user_id=user_id)
        if not revoked:
            raise EntityNotFoundError("APIKey", key_id)

        self.db.commit()
        return APIKeyRevokeResponse(
            id=revoked.id,
            name=revoked.name,
            revoked_at=revoked.revoked_at,
            message="API key has been successfully revoked and can no longer be used.",
        )

    def authenticate_key(self, plain_key: str) -> Tuple[APIKey, User]:
        """
        Validates an incoming API key:
        1. Hashes key using SHA-256.
        2. Retrieves APIKey record with associated user.
        3. Validates not revoked.
        4. Validates not expired.
        5. Validates user account is active.
        6. Updates last_used_at timestamp.
        """
        if not plain_key or not plain_key.strip():
            raise InvalidAPIKeyError("API key header is missing or empty.")

        key_hash = hash_api_key(plain_key)
        api_key = self.key_repo.get_by_hash(key_hash)

        if not api_key:
            raise InvalidAPIKeyError("Invalid API key.")

        now = datetime.now(timezone.utc)

        # Check revocation
        if api_key.revoked_at is not None:
            raise InvalidAPIKeyError(
                f"API key was revoked on {api_key.revoked_at.isoformat()} and can no longer be used."
            )

        # Check expiration
        if api_key.expires_at is not None and api_key.expires_at <= now:
            raise InvalidAPIKeyError(
                f"API key expired on {api_key.expires_at.isoformat()}."
            )

        # Check user account
        if not api_key.user or api_key.user.status != "active":
            raise InvalidAPIKeyError("The user account associated with this API key is inactive or closed.")

        # Update last_used_at
        self.key_repo.touch_last_used(api_key.id)
        self.db.commit()

        return api_key, api_key.user
