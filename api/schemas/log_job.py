from __future__ import annotations

from datetime import datetime
from typing import List, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class LogIngestRequest(BaseModel):
    raw_log: str
    source: Optional[str] = None


class LogIngestResponse(BaseModel):
    job_id: UUID
    status: str
    message: str
    created_at: datetime


class ErrorPatternSchema(BaseModel):
    id: UUID
    error_type: str
    severity: str
    count: int
    root_cause: Optional[str] = None
    suggested_fix: Optional[str] = None
    example_line: Optional[str] = None

    model_config = ConfigDict(from_attributes=True)


class LogJobDetailResponse(BaseModel):
    # validation_alias="id" maps ORM obj.id → response field job_id
    job_id: UUID = Field(validation_alias="id")
    status: str
    source: Optional[str] = None
    error_count: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    patterns: List[ErrorPatternSchema] = []

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LogJobListItem(BaseModel):
    job_id: UUID = Field(validation_alias="id")
    source: Optional[str] = None
    status: str
    error_count: Optional[int] = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class LogJobListResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: List[LogJobListItem]


class AggregatedPattern(BaseModel):
    error_type: str
    total_occurrences: int
    job_count: int
    severity: str
    latest_seen: datetime
    suggested_fix: Optional[str] = None


class PatternsListResponse(BaseModel):
    total: int
    patterns: List[AggregatedPattern]


class HealthResponse(BaseModel):
    status: str
    db: str
    redis: str
    worker: str
