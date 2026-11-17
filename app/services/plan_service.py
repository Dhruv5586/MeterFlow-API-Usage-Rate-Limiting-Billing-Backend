"""
Subscription Plan Service
-------------------------
Business logic for catalog plans.
"""

from typing import List
from sqlalchemy.orm import Session

from app.repositories.plan_repository import PlanRepository
from app.models.plan import SubscriptionPlan


class PlanService:
    def __init__(self, db: Session):
        self.repo = PlanRepository(db)

    def list_active_plans(self) -> List[SubscriptionPlan]:
        return self.repo.get_all_active()
