"""
Payment & Payment Webhook Event Models (SQLAlchemy 2.0)
-------------------------------------------------------
Maps to 'payments' and 'payment_webhook_events' tables in PostgreSQL.
Encapsulates Razorpay order creation, payment signature verification,
webhook event tracking, and idempotency guarantees.
"""

import uuid
from decimal import Decimal
from typing import Optional, Dict, Any
from datetime import datetime, timezone
from sqlalchemy import (
    Text,
    String,
    Numeric,
    DateTime,
    ForeignKey,
    JSON,
    Index,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class Payment(Base):
    """
    Tracks payment orders and gateway settlement status.
    Lifecycle: created -> authorized -> captured | failed | refunded.
    """
    __tablename__ = "payments"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    invoice_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("invoices.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    razorpay_order_id: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True,
    )
    razorpay_payment_id: Mapped[Optional[str]] = mapped_column(
        Text,
        unique=True,
        nullable=True,
        index=True,
    )
    razorpay_signature: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    currency: Mapped[str] = mapped_column(
        String(3),
        nullable=False,
        default="USD",
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="created",
        index=True,
    )
    method: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    error_code: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    error_description: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    captured_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    refunded_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    amount_refunded: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    # Relationships
    user = relationship("User")
    invoice = relationship("Invoice", back_populates="payments")

    def __repr__(self) -> str:
        return f"<Payment {self.id} order={self.razorpay_order_id} pay_id={self.razorpay_payment_id} status={self.status} amount={self.amount} {self.currency}>"


class PaymentWebhookEvent(Base):
    """
    Audit log & idempotency store for Razorpay incoming webhooks.
    Guarantees that an event with event_id is processed at most once.
    """
    __tablename__ = "payment_webhook_events"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    event_id: Mapped[str] = mapped_column(
        Text,
        unique=True,
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        index=True,
    )
    order_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        index=True,
    )
    payment_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
        index=True,
    )
    payload: Mapped[Dict[str, Any]] = mapped_column(
        JSONB().with_variant(JSON(), "sqlite"),
        nullable=False,
        default=dict,
    )
    status: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        default="processed",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
    )

    def __repr__(self) -> str:
        return f"<PaymentWebhookEvent {self.event_id} type={self.event_type} status={self.status}>"
