"""
User Schemas
------------
Pydantic validation models for developer user accounts.
Strictly excludes password hashes and secret key hashes.
"""

import uuid
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, EmailStr, ConfigDict


class APIKeyInfo(BaseModel):
    id: uuid.UUID
    name: str
    key_prefix: str
    created_at: datetime
    expires_at: Optional[datetime] = None
    last_used_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class SubscriptionInfo(BaseModel):
    id: uuid.UUID
    plan_id: uuid.UUID
    plan_code: Optional[str] = None
    plan_name: Optional[str] = None
    status: str
    current_period_start: datetime
    current_period_end: datetime

    model_config = ConfigDict(from_attributes=True)


class UserResponse(BaseModel):
    id: uuid.UUID
    email: EmailStr
    display_name: str
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UserDetailResponse(UserResponse):
    api_keys: List[APIKeyInfo] = []
    subscriptions: List[SubscriptionInfo] = []
