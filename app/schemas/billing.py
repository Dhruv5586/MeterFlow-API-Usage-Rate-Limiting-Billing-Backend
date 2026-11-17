"""
Billing & Invoicing Schemas
---------------------------
Pydantic validation models for invoices, itemized fee breakdowns,
and real-time billing previews with overage calculations.
"""

import uuid
from decimal import Decimal
from typing import Optional, List
from datetime import datetime
from pydantic import BaseModel, Field, ConfigDict


class InvoiceItemResponse(BaseModel):
    id: uuid.UUID
    description: str
    quantity: Decimal
    unit_price: Decimal
    line_amount: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    subscription_id: uuid.UUID
    invoice_number: str
    status: str
    currency: str
    subtotal: Decimal
    tax: Decimal
    total: Decimal
    issued_at: datetime
    due_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class InvoiceDetailResponse(InvoiceResponse):
    items: List[InvoiceItemResponse] = []


class BillingPreviewResponse(BaseModel):
    user_id: uuid.UUID
    subscription_id: uuid.UUID
    plan_code: str
    plan_name: str
    billing_period_start: datetime
    billing_period_end: datetime
    base_plan_price: Decimal
    requests_included: int
    total_requests_recorded: int
    overage_requests: int
    overage_rate_per_1000: Decimal
    overage_amount: Decimal
    estimated_tax: Decimal
    estimated_total: Decimal
    currency: str = "USD"


class GenerateInvoiceRequest(BaseModel):
    subscription_id: Optional[uuid.UUID] = Field(default=None, description="Subscription to bill. Defaults to user's active subscription.")
    period_start: Optional[datetime] = Field(default=None, description="Billing start date. Defaults to current subscription period start.")
    period_end: Optional[datetime] = Field(default=None, description="Billing end date. Defaults to now.")
