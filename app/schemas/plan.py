"""
Subscription Plan Schemas
-------------------------
Request and response models for subscription plans.
"""

import uuid
from decimal import Decimal
from datetime import datetime
from pydantic import BaseModel, ConfigDict


class SubscriptionPlanResponse(BaseModel):
    id: uuid.UUID
    code: str
    name: str
    price: Decimal
    currency: str
    billing_interval: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
