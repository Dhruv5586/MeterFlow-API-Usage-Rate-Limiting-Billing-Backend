"""
Billing & Invoicing API Routes
------------------------------
Endpoints for billing preview, invoice generation with tiered overage fees,
invoice inspection, payment settlement, and daily usage rollups.
"""

import uuid
from typing import List, Optional
from datetime import date
from fastapi import APIRouter, Depends, status, Path, Query
from app.api.dependencies import (
    get_billing_service,
    get_aggregation_service,
    get_current_user,
)
from app.services.billing_service import BillingService
from app.services.aggregation_service import AggregationService
from app.models.user import User
from app.schemas.billing import (
    InvoiceResponse,
    InvoiceDetailResponse,
    BillingPreviewResponse,
    GenerateInvoiceRequest,
)

router = APIRouter(prefix="/billing", tags=["Billing & Invoicing"])


@router.get(
    "/preview",
    response_model=BillingPreviewResponse,
    status_code=status.HTTP_200_OK,
    summary="Preview current billing cycle & estimated overage fees",
    description="Calculates current billing accruals based on active plan pricing, request allowance, and tiered overage fees.",
)
def preview_billing(
    current_user: User = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
):
    return billing_service.preview_billing(user_id=current_user.id)


@router.post(
    "/invoices/generate",
    response_model=InvoiceDetailResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate & finalize monthly invoice",
    description="Calculates base tier fees and itemized overages, saves the invoice in PostgreSQL, and generates line items.",
)
def generate_invoice(
    req: Optional[GenerateInvoiceRequest] = None,
    current_user: User = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
):
    invoice = billing_service.generate_invoice(user_id=current_user.id, req=req)
    return InvoiceDetailResponse.model_validate(invoice)


@router.get(
    "/invoices",
    response_model=List[InvoiceResponse],
    status_code=status.HTTP_200_OK,
    summary="List all invoices for authenticated developer",
    description="Returns all generated invoices with status, subtotal, tax, and total amounts.",
)
def list_invoices(
    current_user: User = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
):
    invoices = billing_service.list_invoices(user_id=current_user.id)
    return [InvoiceResponse.model_validate(inv) for inv in invoices]


@router.get(
    "/invoices/{id}",
    response_model=InvoiceDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Get invoice details with itemized line items",
    description="Retrieves a specific invoice with detailed breakdown of base subscription and overage charges.",
)
def get_invoice(
    id: uuid.UUID = Path(..., description="UUID of the invoice"),
    current_user: User = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
):
    invoice = billing_service.get_invoice(invoice_id=id, user_id=current_user.id)
    return InvoiceDetailResponse.model_validate(invoice)


@router.post(
    "/invoices/{id}/pay",
    response_model=InvoiceDetailResponse,
    status_code=status.HTTP_200_OK,
    summary="Pay/settle an open invoice",
    description="Transitions invoice status to 'paid' and timestamps payment settlement.",
)
def pay_invoice(
    id: uuid.UUID = Path(..., description="UUID of the invoice to settle"),
    current_user: User = Depends(get_current_user),
    billing_service: BillingService = Depends(get_billing_service),
):
    paid_inv = billing_service.pay_invoice(invoice_id=id, user_id=current_user.id)
    return InvoiceDetailResponse.model_validate(paid_inv)


@router.post(
    "/rollup",
    status_code=status.HTTP_200_OK,
    summary="Trigger daily usage aggregation rollup",
    description="Runs dimensional rollups from usage_events into usage_daily. Idempotent.",
)
def trigger_rollup(
    target_date: Optional[date] = Query(default=None, description="Optional target date to aggregate (YYYY-MM-DD)."),
    current_user: User = Depends(get_current_user),
    aggregation_service: AggregationService = Depends(get_aggregation_service),
):
    stats = aggregation_service.rollup_daily_usage(target_date=target_date)
    return {
        "status": "success",
        "message": "Daily usage aggregation completed successfully.",
        "statistics": stats,
    }
