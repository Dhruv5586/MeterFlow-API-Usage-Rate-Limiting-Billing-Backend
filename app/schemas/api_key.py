"""
API Key Schemas
---------------
Pydantic validation models for creating, listing, viewing, and revoking API keys.
"""

import uuid
from datetime import datetime, timezone
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict, field_validator


class APIKeyCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=100, description="Descriptive name for the API key (e.g. 'Production App')")
    expires_in_days: Optional[int] = Field(
        default=None,
        ge=1,
        le=3650,
        description="Optional expiration in days (1 to 3650). If omitted, key does not expire.",
    )

    @field_validator("name", mode="after")
    @classmethod
    def validate_name(cls, v: str) -> str:
        clean = v.strip()
        if not clean:
            raise ValueError("Key name cannot be empty or whitespace only.")
        return clean


class APIKeyCreateResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    api_key: str = Field(description="Plaintext secret API key. WARNING: Shown ONLY ONCE upon creation!")
    created_at: datetime
    expires_at: Optional[datetime] = None
    message: str = "Store this API key safely in your application environment. You will not be able to view it again."

    model_config = ConfigDict(from_attributes=True)


class APIKeyResponse(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    revoked_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None
    is_active: bool

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_orm_model(cls, key_model) -> "APIKeyResponse":
        now = datetime.now(timezone.utc)
        active = (key_model.revoked_at is None) and (key_model.expires_at is None or key_model.expires_at > now)
        return cls(
            id=key_model.id,
            name=key_model.name,
            key_prefix=key_model.key_prefix,
            created_at=key_model.created_at,
            expires_at=key_model.expires_at,
            revoked_at=key_model.revoked_at,
            last_used_at=key_model.last_used_at,
            is_active=active,
        )


class APIKeyRevokeResponse(BaseModel):
    id: uuid.UUID
    name: str
    revoked_at: datetime
    message: str = "API key has been successfully revoked and can no longer be used."
