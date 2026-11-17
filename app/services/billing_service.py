"""
Billing & Invoicing Engine Service
----------------------------------
Calculates base subscription pricing, computes quota overages,
generates itemized invoices, and manages payment settlement lifecycles.
"""

import uuid
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Tuple, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import select, func

from app.core.exceptions import EntityNotFoundError, InvalidParameterError
from app.models.user import User
from app.models.subscription import Subscription
from app.models.plan import SubscriptionPlan
from app.models.usage_event import UsageEvent
from app.models.usage_daily import UsageDaily
from app.models.invoice import Invoice, InvoiceItem
from app.repositories.invoice_repository import InvoiceRepository
from app.schemas.billing import BillingPreviewResponse, GenerateInvoiceRequest

# Pricing catalog rules: quota and overage rate per 1,000 requests
PLAN_BILLING_SPECS: Dict[str, Dict[str, Any]] = {
    "free": {
        "monthly_quota": 10_000,
        "overage_rate_per_1000": Decimal("0.0000"),
        "is_hard_limit": True,
    },
    "pro": {
        "monthly_quota": 100_000,
        "overage_rate_per_1000": Decimal("0.0100"),
        "is_hard_limit": False,
    },
    "enterprise": {
        "monthly_quota": 1_000_000,
        "overage_rate_per_1000": Decimal("0.0050"),
        "is_hard_limit": False,
    },
}


class BillingService:
    def __init__(self, db: Session):
        self.db = db
        self.invoice_repo = InvoiceRepository(db)

    def _get_active_subscription(self, user_id: uuid.UUID, subscription_id: Optional[uuid.UUID] = None) -> Subscription:
        """Finds user's subscription or specified subscription."""
        stmt = (
            select(Subscription)
            .where(Subscription.user_id == user_id)
        )
        if subscription_id:
            stmt = stmt.where(Subscription.id == subscription_id)
        else:
            stmt = stmt.where(Subscription.status == "active").order_by(Subscription.created_at.desc())

        sub = self.db.scalars(stmt).first()
        if not sub:
            raise EntityNotFoundError("Subscription for user", user_id)
        return sub

    def calculate_usage_for_period(
        self,
        subscription_id: uuid.UUID,
        start_date: datetime,
        end_date: datetime,
    ) -> int:
        """
        Calculates total request volume during the specified billing window.
        Inspects pre-aggregated usage_daily first for maximum performance,
        falling back to usage_events if unaggregated.
        """
        # 1. Check usage_daily
        daily_count = self.db.scalar(
            select(func.sum(UsageDaily.request_count))
            .where(
                UsageDaily.subscription_id == subscription_id,
                UsageDaily.usage_date >= start_date.date(),
                UsageDaily.usage_date <= end_date.date(),
            )
        )
        if daily_count is not None and daily_count > 0:
            return int(daily_count)

        # 2. Fallback to usage_events
        raw_count = self.db.scalar(
            select(func.count(UsageEvent.id))
            .where(
                UsageEvent.subscription_id == subscription_id,
                UsageEvent.created_at >= start_date,
                UsageEvent.created_at <= end_date,
            )
        )
        return int(raw_count or 0)

    def preview_billing(
        self,
        user_id: uuid.UUID,
        subscription_id: Optional[uuid.UUID] = None,
    ) -> BillingPreviewResponse:
        """
        Calculates real-time accruals for current billing period.
        """
        sub = self._get_active_subscription(user_id, subscription_id)
        plan = sub.plan
        plan_code = plan.code.lower() if plan else "free"
        specs = PLAN_BILLING_SPECS.get(plan_code, PLAN_BILLING_SPECS["free"])

        start_dt = sub.current_period_start
        end_dt = sub.current_period_end
        now = datetime.now(timezone.utc)

        # Calculate actual usage
        total_requests = self.calculate_usage_for_period(sub.id, start_dt, now)
        quota = specs["monthly_quota"]
        overage_rate_1k = specs["overage_rate_per_1000"]

        overage_requests = max(0, total_requests - quota)
        if overage_requests > 0 and overage_rate_1k > 0:
            overage_amount = (Decimal(overage_requests) / Decimal(1000)) * overage_rate_1k
            overage_amount = overage_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        else:
            overage_amount = Decimal("0.00")

        base_price = Decimal(str(plan.price if plan else 0.00)).quantize(Decimal("0.01"))
        subtotal = base_price + overage_amount
        tax = Decimal("0.00")  # Standard 0% default
        total = subtotal + tax

        return BillingPreviewResponse(
            user_id=user_id,
            subscription_id=sub.id,
            plan_code=plan_code,
            plan_name=plan.name if plan else "Free",
            billing_period_start=start_dt,
            billing_period_end=end_dt,
            base_plan_price=base_price,
            requests_included=quota,
            total_requests_recorded=total_requests,
            overage_requests=overage_requests,
            overage_rate_per_1000=overage_rate_1k,
            overage_amount=overage_amount,
            estimated_tax=tax,
            estimated_total=total,
            currency="USD",
        )

    def generate_invoice(
        self,
        user_id: uuid.UUID,
        req: Optional[GenerateInvoiceRequest] = None,
    ) -> Invoice:
        """
        Calculates line items and creates a finalized invoice record in PostgreSQL.
        """
        sub_id = req.subscription_id if req else None
        sub = self._get_active_subscription(user_id, sub_id)
        plan = sub.plan
        plan_code = plan.code.lower() if plan else "free"
        specs = PLAN_BILLING_SPECS.get(plan_code, PLAN_BILLING_SPECS["free"])

        start_dt = req.period_start if (req and req.period_start) else sub.current_period_start
        end_dt = req.period_end if (req and req.period_end) else datetime.now(timezone.utc)

        # 1. Total usage
        total_requests = self.calculate_usage_for_period(sub.id, start_dt, end_dt)
        quota = specs["monthly_quota"]
        overage_rate_1k = specs["overage_rate_per_1000"]
        overage_requests = max(0, total_requests - quota)

        # 2. Line Items
        line_items = []
        base_price = Decimal(str(plan.price if plan else 0.00)).quantize(Decimal("0.01"))

        # Base tier item
        period_str = f"{start_dt.strftime('%b %d, %Y')} - {end_dt.strftime('%b %d, %Y')}"
        line_items.append({
            "description": f"{plan.name if plan else 'Free'} Plan Base Subscription ({period_str})",
            "quantity": Decimal("1.0000"),
            "unit_price": base_price,
            "line_amount": base_price,
        })

        # Overage item
        overage_amount = Decimal("0.00")
        if overage_requests > 0 and overage_rate_1k > 0:
            overage_amount = (Decimal(overage_requests) / Decimal(1000)) * overage_rate_1k
            overage_amount = overage_amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            unit_price_per_call = (overage_rate_1k / Decimal(1000)).quantize(Decimal("0.0001"))
            line_items.append({
                "description": f"API Requests Overage ({overage_requests:,} calls exceeding {quota:,} limit @ ${overage_rate_1k}/1k)",
                "quantity": Decimal(str(overage_requests)),
                "unit_price": unit_price_per_call,
                "line_amount": overage_amount,
            })

        subtotal = base_price + overage_amount
        tax = Decimal("0.00")
        total = subtotal + tax

        # 3. Create Invoice via Repository
        inv_number = self.invoice_repo.get_next_invoice_number()
        due_at = datetime.now(timezone.utc) + timedelta(days=14)

        invoice = self.invoice_repo.create_invoice(
            user_id=user_id,
            subscription_id=sub.id,
            invoice_number=inv_number,
            subtotal=subtotal,
            tax=tax,
            total=total,
            status="open" if total > 0 else "paid",
            currency="USD",
            issued_at=datetime.now(timezone.utc),
            due_at=due_at if total > 0 else None,
            items=line_items,
        )
        if total == 0:
            invoice.paid_at = datetime.now(timezone.utc)

        self.db.commit()
        self.db.refresh(invoice)
        return invoice

    def list_invoices(self, user_id: uuid.UUID) -> List[Invoice]:
        """Lists all invoices for tenant."""
        return self.invoice_repo.list_invoices_by_user(user_id)

    def get_invoice(self, invoice_id: uuid.UUID, user_id: uuid.UUID) -> Invoice:
        """Retrieves single invoice, ensuring tenant ownership."""
        inv = self.invoice_repo.get_invoice_by_id(invoice_id, user_id=user_id)
        if not inv:
            raise EntityNotFoundError("Invoice", invoice_id)
        return inv

    def pay_invoice(self, invoice_id: uuid.UUID, user_id: uuid.UUID) -> Invoice:
        """Simulates successful payment settlement for an open invoice."""
        inv = self.get_invoice(invoice_id, user_id)
        if inv.status == "paid":
            return inv

        paid_inv = self.invoice_repo.mark_paid(invoice_id, user_id=user_id)
        self.db.commit()
        self.db.refresh(paid_inv)
        return paid_inv
