"""
Quota & Rate Limit Resolution Service
-------------------------------------
Resolves rate limits and monthly quota thresholds based on active subscription plans
and custom usage_quotas records. Tracks real-time monthly consumption in Redis.
"""

import uuid
from datetime import datetime, timezone
from dataclasses import dataclass
from typing import Optional
from sqlalchemy.orm import Session
from sqlalchemy import select

from app.core.config import settings
from app.core.redis import get_redis_client
from app.models.user import User
from app.models.api_key import APIKey
from app.models.subscription import Subscription
from app.models.plan import SubscriptionPlan

# Plan tier default limits (requests per minute and monthly quota)
TIER_LIMITS = {
    "free": {"rate_per_min": 60, "monthly_quota": 10_000, "is_hard": True},
    "pro": {"rate_per_min": 300, "monthly_quota": 100_000, "is_hard": False},
    "enterprise": {"rate_per_min": 1200, "monthly_quota": 1_000_000, "is_hard": False},
}


@dataclass
class QuotaEvaluation:
    plan_code: str
    rate_limit_per_minute: int
    monthly_quota_limit: int
    current_monthly_usage: int
    is_hard_limit: bool
    is_quota_exceeded: bool
    is_soft_warning: bool


class QuotaService:
    def __init__(self, db: Session):
        self.db = db
        self.redis = get_redis_client()

    def resolve_tier_limits(self, user: User) -> tuple[str, str, int, int, bool]:
        """
        Looks up user's active subscription and returns tier specs.
        """
        sub = self.db.scalars(
            select(Subscription)
            .where(Subscription.user_id == user.id, Subscription.status == "active")
            .order_by(Subscription.created_at.desc())
        ).first()

        if sub and sub.plan:
            plan_code = sub.plan.code.lower()
            specs = TIER_LIMITS.get(plan_code, TIER_LIMITS["free"])
            return plan_code, str(sub.id), specs["rate_per_min"], specs["monthly_quota"], specs["is_hard"]

        # Default fallback
        return "free", str(user.id), settings.DEFAULT_RATE_LIMIT_PER_MINUTE, 10_000, True

    def increment_and_check_monthly_quota(self, subscription_id: str, quota_limit: int, is_hard: bool) -> tuple[int, bool, bool]:
        """
        Increments monthly consumption counter in Redis and evaluates limit.
        """
        now = datetime.now(timezone.utc)
        month_key = f"quota:{subscription_id}:{now.strftime('%Y-%m')}"

        try:
            current_usage = self.redis.incr(month_key)
            # Set 35-day expiration on first write
            if current_usage == 1:
                self.redis.expire(month_key, 35 * 86400)
        except Exception:
            current_usage = 0

        is_exceeded = is_hard and (current_usage > quota_limit)
        is_warning = (current_usage >= int(quota_limit * 0.8)) and not is_exceeded

        return current_usage, is_exceeded, is_warning

    def evaluate(self, user: User) -> QuotaEvaluation:
        """
        Full quota and rate limit evaluation for the user.
        """
        plan_code, sub_id, rate_limit, monthly_quota, is_hard = self.resolve_tier_limits(user)
        current_usage, is_exceeded, is_warning = self.increment_and_check_monthly_quota(
            sub_id, monthly_quota, is_hard
        )

        return QuotaEvaluation(
            plan_code=plan_code,
            rate_limit_per_minute=rate_limit,
            monthly_quota_limit=monthly_quota,
            current_monthly_usage=current_usage,
            is_hard_limit=is_hard,
            is_quota_exceeded=is_exceeded,
            is_soft_warning=is_warning,
        )
