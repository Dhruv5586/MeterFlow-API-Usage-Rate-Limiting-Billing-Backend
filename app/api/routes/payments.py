"""
Payment Gateway & Webhook API Routes
------------------------------------
Endpoints for Razorpay order generation, signature verification,
webhook handling, and tenant payment history.
"""

import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, status, Path, Header, Request, Response
from app.api.dependencies import get_current_user, get_payment_service
from app.models.user import User
from app.services.payment_service import PaymentService
from app.schemas.payment import (
    PaymentOrderCreateRequest,
    PaymentOrderResponse,
    PaymentVerifyRequest,
    PaymentResponse,
    WebhookResponse,
)

router = APIRouter(tags=["Payments & Webhooks"])


@router.post(
    "/payments/orders",
    response_model=PaymentOrderResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create Razorpay payment order for invoice",
    description="Validates invoice payable status and ownership, then creates a Razorpay test order.",
)
def create_payment_order(
    req: PaymentOrderCreateRequest,
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    return payment_service.create_payment_order(
        user_id=current_user.id,
        invoice_id=req.invoice_id,
    )


@router.post(
    "/payments/verify",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Verify Razorpay payment signature & settle invoice",
    description="Validates HMAC-SHA256 signature, matches invoice amount/currency, and transitions status to paid.",
)
def verify_payment(
    req: PaymentVerifyRequest,
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    payment = payment_service.verify_payment(
        user_id=current_user.id,
        req=req,
    )
    return PaymentResponse.model_validate(payment)


@router.post(
    "/payments/webhooks/razorpay",
    response_model=WebhookResponse,
    status_code=status.HTTP_200_OK,
    summary="Ingest Razorpay webhook events",
    description="Authenticates incoming webhook via HMAC-SHA256 signature, enforces idempotency, and updates payment state.",
)
async def handle_razorpay_webhook(
    request: Request,
    x_razorpay_signature: Optional[str] = Header(None, alias="X-Razorpay-Signature"),
    payment_service: PaymentService = Depends(get_payment_service),
):
    raw_body = await request.body()
    return payment_service.process_webhook(
        raw_body=raw_body,
        signature_header=x_razorpay_signature,
    )


@router.get(
    "/payments/{payment_id}",
    response_model=PaymentResponse,
    status_code=status.HTTP_200_OK,
    summary="Get payment details by ID",
    description="Retrieves a specific payment record. Restricted to the payment owner.",
)
def get_payment(
    payment_id: uuid.UUID = Path(..., description="UUID of the payment record"),
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    payment = payment_service.get_payment_by_id(
        payment_id=payment_id,
        user_id=current_user.id,
    )
    return PaymentResponse.model_validate(payment)


@router.get(
    "/invoices/{invoice_id}/payments",
    response_model=List[PaymentResponse],
    status_code=status.HTTP_200_OK,
    summary="List payments for an invoice",
    description="Retrieves all payment transactions associated with a given invoice for the authenticated user.",
)
def list_invoice_payments(
    invoice_id: uuid.UUID = Path(..., description="UUID of the invoice"),
    current_user: User = Depends(get_current_user),
    payment_service: PaymentService = Depends(get_payment_service),
):
    payments = payment_service.list_invoice_payments(
        invoice_id=invoice_id,
        user_id=current_user.id,
    )
    return [PaymentResponse.model_validate(p) for p in payments]
