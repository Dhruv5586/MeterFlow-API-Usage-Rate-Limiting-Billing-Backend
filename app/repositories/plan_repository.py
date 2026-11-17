"""
Subscription Plan Repository
----------------------------
Encapsulates data access queries for subscription catalog plans.
"""

import uuid
from typing import List, Optional
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.plan import SubscriptionPlan


class PlanRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_all_active(self) -> List[SubscriptionPlan]:
        """
        Retrieves all currently active subscription plans ordered by price ascending.
        """
        stmt = (
            select(SubscriptionPlan)
            .where(SubscriptionPlan.is_active == True)
            .order_by(SubscriptionPlan.price.asc())
        )
        return list(self.db.scalars(stmt).all())

    def get_by_id(self, plan_id: uuid.UUID) -> Optional[SubscriptionPlan]:
        stmt = select(SubscriptionPlan).where(SubscriptionPlan.id == plan_id)
        return self.db.scalars(stmt).first()

    def get_by_code(self, code: str) -> Optional[SubscriptionPlan]:
        stmt = select(SubscriptionPlan).where(SubscriptionPlan.code == code.lower())
        return self.db.scalars(stmt).first()
