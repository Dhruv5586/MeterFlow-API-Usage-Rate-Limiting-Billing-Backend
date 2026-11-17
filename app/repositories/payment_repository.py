"""
Payment Repository (Data Access Layer)
--------------------------------------
Encapsulates all database queries and transactions for payments,
gateway order references, and webhook idempotency events.
"""

import uuid
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy import select, desc
from sqlalchemy.orm import Session

from app.models.payment import Payment, PaymentWebhookEvent


class PaymentRepository:
    def __init__(self, session: Session):
        self.session = session

    def create_payment(
        self,
        user_id: uuid.UUID,
        invoice_id: uuid.UUID,
        razorpay_order_id: str,
        amount: Decimal,
        currency: str,
        status: str = "created",
    ) -> Payment:
        """Persists a new payment order record."""
        payment = Payment(
            user_id=user_id,
            invoice_id=invoice_id,
            razorpay_order_id=razorpay_order_id,
            amount=amount,
            currency=currency,
            status=status,
        )
        self.session.add(payment)
        self.session.flush()
        return payment

    def get_payment_by_id(self, payment_id: uuid.UUID) -> Optional[Payment]:
        """Retrieves a payment by its primary key UUID."""
        return self.session.get(Payment, payment_id)

    def get_payment_by_order_id(self, order_id: str) -> Optional[Payment]:
        """Retrieves a payment by Razorpay order ID."""
        stmt = select(Payment).where(Payment.razorpay_order_id == order_id)
        return self.session.scalars(stmt).first()

    def get_payment_by_razorpay_payment_id(self, payment_id: str) -> Optional[Payment]:
        """Retrieves a payment by Razorpay payment ID."""
        stmt = select(Payment).where(Payment.razorpay_payment_id == payment_id)
        return self.session.scalars(stmt).first()

    def get_active_order_for_invoice(self, invoice_id: uuid.UUID) -> Optional[Payment]:
        """
        Finds an active uncaptured payment order for this invoice.
        Used to prevent duplicate active orders if client re-submits order creation.
        """
        stmt = (
            select(Payment)
            .where(
                Payment.invoice_id == invoice_id,
                Payment.status.in_(["created", "authorized"]),
            )
            .order_by(desc(Payment.created_at))
        )
        return self.session.scalars(stmt).first()

    def list_payments_by_invoice(self, invoice_id: uuid.UUID) -> List[Payment]:
        """Returns all payment attempts for a given invoice."""
        stmt = (
            select(Payment)
            .where(Payment.invoice_id == invoice_id)
            .order_by(desc(Payment.created_at))
        )
        return list(self.session.scalars(stmt).all())

    def list_payments_by_user(self, user_id: uuid.UUID) -> List[Payment]:
        """Returns all payments executed by a tenant."""
        stmt = (
            select(Payment)
            .where(Payment.user_id == user_id)
            .order_by(desc(Payment.created_at))
        )
        return list(self.session.scalars(stmt).all())

    def is_webhook_event_processed(self, event_id: str) -> bool:
        """Checks if a webhook event ID has already been recorded (idempotency check)."""
        stmt = select(PaymentWebhookEvent.id).where(PaymentWebhookEvent.event_id == event_id)
        return self.session.scalars(stmt).first() is not None

    def save_webhook_event(
        self,
        event_id: str,
        event_type: str,
        order_id: Optional[str] = None,
        payment_id: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
        status: str = "processed",
    ) -> PaymentWebhookEvent:
        """Records an incoming webhook event to guarantee at-most-once processing."""
        event = PaymentWebhookEvent(
            event_id=event_id,
            event_type=event_type,
            order_id=order_id,
            payment_id=payment_id,
            payload=payload or {},
            status=status,
        )
        self.session.add(event)
        self.session.flush()
        return event
