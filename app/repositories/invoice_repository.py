"""
Invoice Repository
------------------
Data access layer for tenant billing records and itemized line items.
Eliminates N+1 queries by eager loading InvoiceItem relationships.
"""

import uuid
from decimal import Decimal
from typing import Optional, List, Tuple
from datetime import datetime, timezone
from sqlalchemy import select, func, update
from sqlalchemy.orm import Session, selectinload, joinedload

from app.models.invoice import Invoice, InvoiceItem


class InvoiceRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_next_invoice_number(self) -> str:
        """
        Generates a sequential human-readable invoice identifier:
        Format: INV-YYYYMM-XXXX (e.g. INV-202611-0001)
        """
        now = datetime.now(timezone.utc)
        prefix = f"INV-{now.strftime('%Y%m')}"
        
        # Count existing invoices with this monthly prefix
        count = self.db.scalar(
            select(func.count(Invoice.id))
            .where(Invoice.invoice_number.like(f"{prefix}-%"))
        ) or 0

        seq = count + 1
        return f"{prefix}-{seq:04d}"

    def create_invoice(
        self,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
        invoice_number: str,
        subtotal: Decimal,
        tax: Decimal,
        total: Decimal,
        status: str = "open",
        currency: str = "USD",
        issued_at: Optional[datetime] = None,
        due_at: Optional[datetime] = None,
        items: Optional[List[dict]] = None,
    ) -> Invoice:
        """
        Creates an invoice header and associated itemized line items atomically.
        """
        now = issued_at or datetime.now(timezone.utc)
        
        invoice = Invoice(
            user_id=user_id,
            subscription_id=subscription_id,
            invoice_number=invoice_number,
            status=status,
            currency=currency,
            subtotal=subtotal,
            tax=tax,
            total=total,
            issued_at=now,
            due_at=due_at,
        )
        self.db.add(invoice)
        self.db.flush()

        if items:
            for item_data in items:
                line_item = InvoiceItem(
                    invoice_id=invoice.id,
                    description=item_data["description"],
                    quantity=Decimal(str(item_data.get("quantity", 1))),
                    unit_price=Decimal(str(item_data.get("unit_price", 0))),
                    line_amount=Decimal(str(item_data["line_amount"])),
                )
                self.db.add(line_item)

        self.db.flush()
        return invoice

    def get_invoice_by_id(self, invoice_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> Optional[Invoice]:
        """
        Retrieves a single invoice by UUID with line items and subscription eager loaded.
        """
        stmt = (
            select(Invoice)
            .options(
                selectinload(Invoice.items),
                joinedload(Invoice.subscription),
            )
            .where(Invoice.id == invoice_id)
        )
        if user_id:
            stmt = stmt.where(Invoice.user_id == user_id)
        return self.db.scalars(stmt).first()

    def list_invoices_by_user(self, user_id: uuid.UUID) -> List[Invoice]:
        """
        Retrieves all invoices for a tenant ordered newest first.
        """
        stmt = (
            select(Invoice)
            .options(selectinload(Invoice.items))
            .where(Invoice.user_id == user_id)
            .order_by(Invoice.issued_at.desc())
        )
        return list(self.db.scalars(stmt).all())

    def mark_paid(self, invoice_id: uuid.UUID, user_id: Optional[uuid.UUID] = None) -> Optional[Invoice]:
        """
        Transitions invoice status to 'paid' and timestamps paid_at.
        """
        invoice = self.get_invoice_by_id(invoice_id, user_id=user_id)
        if not invoice:
            return None

        invoice.status = "paid"
        invoice.paid_at = datetime.now(timezone.utc)
        self.db.flush()
        return invoice
