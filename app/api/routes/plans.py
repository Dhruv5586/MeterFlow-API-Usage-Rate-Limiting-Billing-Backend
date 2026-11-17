"""
Subscription Plans Router
-------------------------
Endpoints for viewing catalog subscription plans.
"""

from typing import List
from fastapi import APIRouter, Depends, status
from app.schemas.plan import SubscriptionPlanResponse
from app.services.plan_service import PlanService
from app.api.dependencies import get_plan_service

router = APIRouter(prefix="/plans", tags=["Subscription Plans"])


@router.get(
    "",
    response_model=List[SubscriptionPlanResponse],
    status_code=status.HTTP_200_OK,
    summary="List Active Subscription Plans",
    description="Returns all available subscription plans (Free, Pro, Enterprise) ordered by price.",
)
def list_plans(
    service: PlanService = Depends(get_plan_service),
) -> List[SubscriptionPlanResponse]:
    plans = service.list_active_plans()
    return [SubscriptionPlanResponse.model_validate(p) for p in plans]
