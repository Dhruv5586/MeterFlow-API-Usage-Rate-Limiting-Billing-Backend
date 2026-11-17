"""
Usage Service
-------------
Business logic for usage metrics and event queries.
"""

import uuid
from typing import Optional, List, Tuple, Dict, Any
from datetime import datetime
from sqlalchemy.orm import Session

from app.repositories.usage_repository import UsageRepository
from app.models.usage_event import UsageEvent


class UsageService:
    def __init__(self, db: Session):
        self.repo = UsageRepository(db)

    def list_events(
        self,
        offset: int,
        limit: int,
        user_id: Optional[uuid.UUID] = None,
        api_key_id: Optional[uuid.UUID] = None,
        endpoint: Optional[str] = None,
        http_method: Optional[str] = None,
    ) -> Tuple[List[UsageEvent], int]:
        return self.repo.get_events(
            offset=offset,
            limit=limit,
            user_id=user_id,
            api_key_id=api_key_id,
            endpoint=endpoint,
            http_method=http_method,
        )

    def get_summary(
        self,
        user_id: Optional[uuid.UUID] = None,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        return self.repo.get_usage_summary(
            user_id=user_id,
            start_date=start_date,
            end_date=end_date,
        )
