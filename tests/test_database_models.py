"""
Integration Tests for SQLAlchemy 2.0 Database Connection & ORM Models
"""

import pytest
from sqlalchemy import select
from app.core.config import settings
from app.core.database import SessionLocal, check_database_health
from app.models.user import User
from app.models.plan import SubscriptionPlan
from app.models.api_key import APIKey
from app.models.subscription import Subscription


def test_settings_database_url_driver():
    """Verify that pydantic-settings normalized the driver prefix for psycopg 3."""
    assert "postgresql+psycopg://" in settings.DATABASE_URL
    assert settings.APP_NAME == "MeterFlow"


def test_database_health_check():
    """Verify that check_database_health returns True against live Neon PostgreSQL."""
    is_healthy = check_database_health()
    assert is_healthy is True


def test_query_subscription_plans_orm():
    """Verify that subscription plans can be selected as SQLAlchemy ORM objects."""
    with SessionLocal() as session:
        stmt = select(SubscriptionPlan).order_by(SubscriptionPlan.price)
        plans = session.scalars(stmt).all()
        assert len(plans) >= 3
        codes = [p.code for p in plans]
        assert "free" in codes
        assert "pro" in codes
        assert "enterprise" in codes

        # Type checks
        free_plan = next(p for p in plans if p.code == "free")
        assert free_plan.price == 0.00
        assert free_plan.currency == "USD"
        assert free_plan.is_active is True


def test_query_users_and_relationships_orm():
    """Verify that demo users and their related API keys and subscriptions load via ORM."""
    with SessionLocal() as session:
        stmt = select(User).where(User.email.in_([
            "admin@technova.io",
            "engineering@cloudsphere.dev",
            "ops@databridge.net",
        ]))
        demo_users = session.scalars(stmt).all()
        assert len(demo_users) == 3

        for user in demo_users:
            assert user.status == "active"
            assert user.id is not None
            # Check ORM relationship loading
            assert len(user.api_keys) >= 1
            assert len(user.subscriptions) >= 1

            # Check that API key prefix matches expected format
            api_key = user.api_keys[0]
            assert api_key.key_prefix.startswith("mf_live_")
            assert len(api_key.key_hash) == 64

            # Check subscription plan relationship
            sub = user.subscriptions[0]
            assert sub.status == "active"
            assert sub.plan is not None
            assert sub.plan.code in ("free", "pro", "enterprise")
