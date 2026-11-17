"""
Usage Daily Model (SQLAlchemy 2.0)
----------------------------------
Maps to the 'usage_daily' table in PostgreSQL.
Stores pre-aggregated daily metrics broken down by dimensions:
(usage_date, subscription_id, api_key_id, endpoint, http_method)
"""

import uuid
from datetime import date, datetime, timezone
from sqlalchemy import Text, BigInteger, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UsageDaily(Base):
    __tablename__ = "usage_daily"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="RESTRICT"),
        nullable=False,
    )
    usage_date: Mapped[date] = mapped_column(
        Date,
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    http_method: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    request_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    successful_request_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    error_request_count: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    response_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    latency_sum_ms: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
        default=0,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
    )

    __table_args__ = (
        UniqueConstraint(
            "usage_date", "subscription_id", "api_key_id", "endpoint", "http_method",
            name="usage_daily_dimensions_uq",
        ),
    )

    # Relationships
    user = relationship("User")
    subscription = relationship("Subscription")
    api_key = relationship("APIKey")

    def __repr__(self) -> str:
        return f"<UsageDaily date={self.usage_date} endpoint={self.endpoint} count={self.request_count}>"
