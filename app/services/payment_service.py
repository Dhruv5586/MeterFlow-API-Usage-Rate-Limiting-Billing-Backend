"""
Payment Service (Business Logic Layer)
--------------------------------------
Orchestrates Razorpay order creation, payment signature verification,
idempotent webhook processing, status transitions, and audit records.
"""

import json
import uuid
import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.exceptions import (
    EntityNotFoundError,
    AuthorizationError,
    InvalidParameterError,
)
from app.models.payment import Payment, PaymentWebhookEvent
from app.models.invoice import Invoice
from app.repositories.payment_repository import PaymentRepository
from app.repositories.invoice_repository import InvoiceRepository
from app.services.razorpay_service import RazorpayService
from app.schemas.payment import (
    PaymentOrderResponse,
    PaymentVerifyRequest,
    WebhookResponse,
)

logger = logging.getLogger("meterflow.payments")


class PaymentService:
    def __init__(
        self,
        session: Session,
        payment_repo: Optional[PaymentRepository] = None,
        invoice_repo: Optional[InvoiceRepository] = None,
        razorpay_service: Optional[RazorpayService] = None,
    ):
        self.session = session
        self.payment_repo = payment_repo or PaymentRepository(session)
        self.invoice_repo = invoice_repo or InvoiceRepository(session)
        self.razorpay_service = razorpay_service or RazorpayService()

    def create_payment_order(
        self,
        user_id: uuid.UUID,
        invoice_id: uuid.UUID,
    ) -> PaymentOrderResponse:
        """
        Validates invoice ownership and eligibility, then initiates a Razorpay test order.
        Reuses existing active orders to prevent duplicate pending orders.
        """
        # 1. Verify invoice existence and ownership
        invoice = self.invoice_repo.get_invoice_by_id(invoice_id)
        if not invoice:
            raise EntityNotFoundError("Invoice", invoice_id)

        if invoice.user_id != user_id:
            logger.warning(f"User {user_id} attempted unauthorized access to invoice {invoice_id}")
            raise AuthorizationError("You do not have permission to pay this invoice.")

        # 2. Check if already paid
        if invoice.status == "paid":
            raise InvalidParameterError("Invoice is already paid.")

        if invoice.status in ("void", "uncollectible"):
            raise InvalidParameterError(f"Invoice status is '{invoice.status}' and cannot be paid.")

        # 3. Check payable amount
        if invoice.total <= Decimal("0.00"):
            raise InvalidParameterError("Invoice total must be greater than 0 to create a payment order.")

        # Convert to minor units (e.g. $29.00 -> 2900 cents)
        amount_minor = self.razorpay_service.amount_to_minor_units(invoice.total, invoice.currency)

        # 4. Check for existing active pending order to avoid duplicate orders
        existing_order = self.payment_repo.get_active_order_for_invoice(invoice.id)
        if existing_order and existing_order.amount == invoice.total:
            logger.info(f"Reusing active order {existing_order.razorpay_order_id} for invoice {invoice.id}")
            return PaymentOrderResponse(
                order_id=existing_order.razorpay_order_id,
                amount=amount_minor,
                currency=invoice.currency,
                key_id=self.razorpay_service.key_id,
                invoice_id=invoice.id,
                invoice_number=invoice.invoice_number,
            )

        # 5. Create order with Razorpay Gateway
        notes = {
            "invoice_id": str(invoice.id),
            "invoice_number": invoice.invoice_number,
            "user_id": str(user_id),
        }
        rzp_order = self.razorpay_service.create_order(
            amount_minor=amount_minor,
            currency=invoice.currency,
            receipt=invoice.invoice_number,
            notes=notes,
        )

        order_id = rzp_order["id"]

        # 6. Persist payment record in DB
        self.payment_repo.create_payment(
            user_id=user_id,
            invoice_id=invoice.id,
            razorpay_order_id=order_id,
            amount=invoice.total,
            currency=invoice.currency,
            status="created",
        )
        self.session.commit()

        logger.info(f"Created payment order {order_id} for invoice {invoice.invoice_number}")
        return PaymentOrderResponse(
            order_id=order_id,
            amount=amount_minor,
            currency=invoice.currency,
            key_id=self.razorpay_service.key_id,
            invoice_id=invoice.id,
            invoice_number=invoice.invoice_number,
        )

    def verify_payment(
        self,
        user_id: uuid.UUID,
        req: PaymentVerifyRequest,
    ) -> Payment:
        """
        Verifies cryptographic signature, matches amount and currency against invoice,
        and transactionally marks payment captured and invoice paid.
        """
        # 1. Cryptographic HMAC-SHA256 signature verification
        is_valid = self.razorpay_service.verify_payment_signature(
            order_id=req.razorpay_order_id,
            payment_id=req.razorpay_payment_id,
            signature=req.razorpay_signature,
        )
        if not is_valid:
            logger.warning(f"Signature verification failed for order {req.razorpay_order_id}")
            raise InvalidParameterError("Invalid payment signature.")

        # 2. Retrieve payment record
        payment = self.payment_repo.get_payment_by_order_id(req.razorpay_order_id)
        if not payment:
            raise EntityNotFoundError("Payment order", req.razorpay_order_id)

        # 3. Ownership check
        if payment.user_id != user_id:
            raise AuthorizationError("You do not have permission to verify this payment.")

        # 4. Check for duplicate verification (Idempotency)
        if payment.status == "captured":
            logger.info(f"Payment {payment.id} already captured. Returning existing record.")
            return payment

        # 5. Verify invoice exists and currency/amount match
        invoice = self.invoice_repo.get_invoice_by_id(payment.invoice_id)
        if not invoice:
            raise EntityNotFoundError("Invoice", payment.invoice_id)

        if payment.amount != invoice.total:
            raise InvalidParameterError(
                f"Amount mismatch: order is for {payment.amount} but invoice is {invoice.total}."
            )

        if payment.currency != invoice.currency:
            raise InvalidParameterError(
                f"Currency mismatch: order is for {payment.currency} but invoice is {invoice.currency}."
            )

        # 6. Transactional state transition
        try:
            now = datetime.now(timezone.utc)
            payment.razorpay_payment_id = req.razorpay_payment_id
            payment.razorpay_signature = req.razorpay_signature
            payment.status = "captured"
            payment.captured_at = now
            payment.updated_at = now

            invoice.status = "paid"
            invoice.paid_at = now

            self.session.commit()
            self.session.refresh(payment)
            logger.info(f"Payment {payment.id} successfully captured. Invoice {invoice.invoice_number} paid.")
            return payment
        except Exception as exc:
            self.session.rollback()
            logger.error(f"Transaction failed during payment verification: {exc}")
            raise

    def process_webhook(
        self,
        raw_body: bytes,
        signature_header: Optional[str],
    ) -> WebhookResponse:
        """
        Validates webhook authenticity, guarantees idempotency via event storage,
        and applies state updates without allowing late failure events to override captured payments.
        """
        # 1. Verify webhook signature
        if not signature_header:
            raise InvalidParameterError("Missing X-Razorpay-Signature header.")

        is_valid = self.razorpay_service.verify_webhook_signature(
            raw_body=raw_body,
            signature_header=signature_header,
        )
        if not is_valid:
            logger.warning("Razorpay webhook signature verification failed.")
            raise InvalidParameterError("Invalid webhook signature.")

        # 2. Parse payload
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception as exc:
            raise InvalidParameterError(f"Malformed JSON webhook payload: {exc}")

        event_id = payload.get("event_id") or payload.get("id")
        if not event_id:
            # Fallback event key if gateway payload lacks top-level id
            created_at = payload.get("created_at", "0")
            event_type_fallback = payload.get("event", "unknown")
            event_id = f"evt_{event_type_fallback}_{created_at}"

        event_type = payload.get("event", "unknown")

        # 3. Idempotency Check: Reject already-processed events
        if self.payment_repo.is_webhook_event_processed(event_id):
            logger.info(f"Webhook event {event_id} already processed. Ignoring duplicate.")
            return WebhookResponse(
                status="ignored",
                message="Duplicate event already processed.",
                event_id=event_id,
                event_type=event_type,
            )

        # 4. Extract entities
        payload_data = payload.get("payload", {})
        payment_entity = payload_data.get("payment", {}).get("entity", {})
        refund_entity = payload_data.get("refund", {}).get("entity", {})

        order_id = payment_entity.get("order_id") or refund_entity.get("order_id")
        payment_id = payment_entity.get("id") or refund_entity.get("payment_id")

        try:
            payment: Optional[Payment] = None
            if payment_id:
                payment = self.payment_repo.get_payment_by_razorpay_payment_id(payment_id)
            if not payment and order_id:
                payment = self.payment_repo.get_payment_by_order_id(order_id)

            now = datetime.now(timezone.utc)

            # 5. Handle event types safely
            if event_type == "payment.authorized":
                if payment and payment.status == "created":
                    payment.status = "authorized"
                    if payment_id:
                        payment.razorpay_payment_id = payment_id
                    payment.updated_at = now

            elif event_type == "payment.captured":
                if payment:
                    payment.status = "captured"
                    if payment_id:
                        payment.razorpay_payment_id = payment_id
                    payment.captured_at = now
                    payment.updated_at = now

                    # Settle invoice transactionally
                    if payment.invoice and payment.invoice.status != "paid":
                        payment.invoice.status = "paid"
                        payment.invoice.paid_at = now

            elif event_type == "payment.failed":
                if payment:
                    # CRITICAL: Prevent late failure events from reverting captured or refunded payments
                    if payment.status in ("captured", "refunded"):
                        logger.warning(
                            f"Ignoring late payment.failed event for already {payment.status} payment {payment.id}"
                        )
                    else:
                        payment.status = "failed"
                        payment.error_code = payment_entity.get("error_code")
                        payment.error_description = payment_entity.get("error_description")
                        payment.updated_at = now

            elif event_type in ("refund.created", "refund.processed"):
                if payment:
                    payment.status = "refunded"
                    payment.refunded_at = now
                    payment.updated_at = now
                    amount_minor = refund_entity.get("amount", 0)
                    if amount_minor:
                        payment.amount_refunded = self.razorpay_service.minor_units_to_amount(
                            amount_minor, payment.currency
                        )

            # 6. Record processed webhook event for idempotency
            self.payment_repo.save_webhook_event(
                event_id=event_id,
                event_type=event_type,
                order_id=order_id,
                payment_id=payment_id,
                payload=payload,
                status="processed",
            )
            self.session.commit()

            logger.info(f"Webhook {event_id} ({event_type}) successfully processed.")
            return WebhookResponse(
                status="success",
                message=f"Processed event {event_type}",
                event_id=event_id,
                event_type=event_type,
            )
        except Exception as exc:
            self.session.rollback()
            logger.error(f"Error processing webhook {event_id}: {exc}")
            raise

    def get_payment_by_id(self, payment_id: uuid.UUID, user_id: uuid.UUID) -> Payment:
        """Retrieves a payment, verifying tenant authorization."""
        payment = self.payment_repo.get_payment_by_id(payment_id)
        if not payment:
            raise EntityNotFoundError("Payment", payment_id)

        if payment.user_id != user_id:
            raise AuthorizationError("You do not have permission to view this payment.")

        return payment

    def list_invoice_payments(self, invoice_id: uuid.UUID, user_id: uuid.UUID) -> List[Payment]:
        """Lists all payment records for an invoice, ensuring tenant ownership."""
        invoice = self.invoice_repo.get_invoice_by_id(invoice_id)
        if not invoice:
            raise EntityNotFoundError("Invoice", invoice_id)

        if invoice.user_id != user_id:
            raise AuthorizationError("You do not have permission to view payments for this invoice.")

        return self.payment_repo.list_payments_by_invoice(invoice_id)
