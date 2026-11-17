"""
Usage Event Model (SQLAlchemy 2.0)
----------------------------------
Maps to the 'usage_events' table in PostgreSQL.
"""

import uuid
from typing import Optional
from datetime import datetime
from sqlalchemy import String, Text, SmallInteger, Integer, BigInteger, DateTime, ForeignKey
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base


class UsageEvent(Base):
    __tablename__ = "usage_events"

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
    api_key_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("api_keys.id", ondelete="RESTRICT"),
        nullable=False,
    )
    subscription_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("subscriptions.id", ondelete="RESTRICT"),
        nullable=False,
    )
    http_method: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    endpoint: Mapped[str] = mapped_column(
        Text,
        nullable=False,
    )
    status_code: Mapped[int] = mapped_column(
        SmallInteger,
        nullable=False,
    )
    latency_ms: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )
    response_size_bytes: Mapped[int] = mapped_column(
        BigInteger,
        nullable=False,
    )
    source_server_id: Mapped[Optional[str]] = mapped_column(
        Text,
        nullable=True,
    )
    source_record_key: Mapped[Optional[str]] = mapped_column(
        Text,
        unique=True,
        nullable=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )

    # Relationships
    user = relationship("User", back_populates="usage_events")
    api_key = relationship("APIKey", back_populates="usage_events")
    subscription = relationship("Subscription", back_populates="usage_events")

    def __repr__(self) -> str:
        return f"<UsageEvent method={self.http_method} endpoint={self.endpoint} status={self.status_code}>"
