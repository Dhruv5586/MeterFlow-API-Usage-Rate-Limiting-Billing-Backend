"""
Usage & Health Schemas
----------------------
Pydantic models for API events, summaries, and system health checks.
"""

import uuid
from typing import Optional
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class HealthResponse(BaseModel):
    status: str = Field(default="healthy", description="Application status")
    version: str = Field(default="0.1.0", description="API version")
    server_time: datetime = Field(description="Current server UTC timestamp")
    database_connected: bool = Field(description="Live database connectivity status")
    redis_connected: bool = Field(default=True, description="Redis connectivity status")
    rate_limiter_backend: str = Field(default="redis", description="Active rate limiter storage backend")


class UsageEventResponse(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    api_key_id: uuid.UUID
    subscription_id: uuid.UUID
    http_method: str
    endpoint: str
    status_code: int
    latency_ms: int
    response_size_bytes: int
    source_server_id: Optional[str] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class UsageSummaryResponse(BaseModel):
    total_requests: int
    successful_requests: int
    failed_requests: int
    average_latency_ms: float
    total_response_bytes: int
    period_start: Optional[datetime] = None
    period_end: Optional[datetime] = None
