"""
Usage Repository
----------------
Encapsulates queries for raw usage events and aggregation metrics.
"""

import uuid
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from sqlalchemy import select, func, case, and_
from sqlalchemy.orm import Session

from app.models.usage_event import UsageEvent


class UsageRepository:
    def __init__(self, db: Session):
        self.db = db

    def get_events(
        self,
        offset: int = 0,
        limit: int = 20,
        user_id: Optional[uuid.UUID] = None,
        api_key_id: Optional[uuid.UUID] = None,
        endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
    ) -> Tuple[List[UsageEvent], int]:
        """
        Retrieves paginated usage events with optional tenant and endpoint filters.
        """
        filters = []
        if user_id:
            filters.append(UsageEvent.user_id == user_id)
        if api_key_id:
            filters.append(UsageEvent.api_key_id == api_key_id)
        if endpoint:
            filters.append(UsageEvent.endpoint == endpoint)
        if http_method:
            filters.append(UsageEvent.http_method == http_method.upper())

        count_stmt = select(func.count(UsageEvent.id))
        if filters:
            count_stmt = count_stmt.where(and_(*filters))
        total = self.db.scalar(count_stmt) or 0

        stmt = select(UsageEvent)
        if filters:
            stmt = stmt.where(and_(*filters))
        stmt = stmt.order_by(UsageEvent.created_at.desc()).offset(offset).limit(limit)

        events = list(self.db.scalars(stmt).all())
        return events, total

    def get_usage_summary(
        self,
        user_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Calculates aggregate usage statistics in a single efficient SQL query.
        """
        filters = []
        if user_id:
            filters.append(UsageEvent.user_id == user_id)
        if start_date:
            filters.append(UsageEvent.created_at >= start_date)
        if end_date:
            filters.append(UsageEvent.created_at <= end_date)

        stmt = select(
            func.count(UsageEvent.id).label("total_requests"),
            func.coalesce(
                func.sum(case((UsageEvent.status_code < 400, 1), else_=0)), 0
            ).label("successful_requests"),
            func.coalesce(
                func.sum(case((UsageEvent.status_code >= 400, 1), else_=0)), 0
            ).label("failed_requests"),
            func.coalesce(func.avg(UsageEvent.latency_ms), 0.0).label("avg_latency"),
            func.coalesce(func.sum(UsageEvent.response_size_bytes), 0).label("total_bytes"),
        )

        if filters:
            stmt = stmt.where(and_(*filters))

        row = self.db.execute(stmt).one()
        return {
            "total_requests": int(row.total_requests or 0),
            "successful_requests": int(row.successful_requests or 0),
            "failed_requests": int(row.failed_requests or 0),
            "average_latency_ms": round(float(row.avg_latency or 0.0), 2),
            "total_response_bytes": int(row.total_bytes or 0),
            "period_start": start_date,
            "period_end": end_date,
        }
