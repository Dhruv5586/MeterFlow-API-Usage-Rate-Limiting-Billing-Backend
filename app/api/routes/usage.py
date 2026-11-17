"""
API Usage Router
----------------
Endpoints for usage event analytics, queries, and summaries.
"""

import uuid
from typing import Optional
from datetime import datetime
from fastapi import APIRouter, Depends, Query, status
from app.schemas.usage import UsageSummaryResponse, UsageEventResponse
from app.schemas.common import Page, PaginationParams
from app.services.usage_service import UsageService
from app.api.dependencies import get_usage_service, get_pagination

router = APIRouter(prefix="/usage", tags=["API Usage & Metering"])


@router.get(
    "/summary",
    response_model=UsageSummaryResponse,
    status_code=status.HTTP_200_OK,
    summary="Get Usage Aggregation Summary",
    description="Calculates total requests, successful vs failed counts, average latency, and total bytes.",
)
def get_usage_summary(
    user_id: Optional[uuid.UUID] = Query(default=None, description="Filter summary by developer user UUID"),
    start_date: Optional[datetime] = Query(default=None, description="Start timestamp (ISO-8601 UTC)"),
    end_date: Optional[datetime] = Query(default=None, description="End timestamp (ISO-8601 UTC)"),
    service: UsageService = Depends(get_usage_service),
) -> UsageSummaryResponse:
    summary = service.get_summary(user_id=user_id, start_date=start_date, end_date=end_date)
    return UsageSummaryResponse(**summary)


@router.get(
    "/events",
    response_model=Page[UsageEventResponse],
    status_code=status.HTTP_200_OK,
    summary="List API Usage Events (Paginated)",
    description="Returns individual API request events with status codes, latency in ms, and response payload size.",
)
def list_usage_events(
    user_id: Optional[uuid.UUID] = Query(default=None, description="Filter events by user UUID"),
    api_key_id: Optional[uuid.UUID] = Query(default=None, description="Filter events by API key UUID"),
    endpoint: Optional[str] = Query(default=None, description="Filter events by exact endpoint path"),
    http_method: Optional[str] = Query(default=None, description="Filter by HTTP method (GET, POST, etc.)"),
    pagination: PaginationParams = Depends(get_pagination),
    service: UsageService = Depends(get_usage_service),
) -> Page[UsageEventResponse]:
    events, total = service.list_events(
        offset=pagination.offset,
        limit=pagination.size,
        user_id=user_id,
        api_key_id=api_key_id,
        endpoint=endpoint,
        http_method=http_method,
    )
    items = [UsageEventResponse.model_validate(e) for e in events]
    return Page.create(items=items, total=total, page=pagination.page, size=pagination.size)
