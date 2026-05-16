from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict


class InsightResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    property_id: int
    kind: str
    severity: str
    title: str
    summary: str
    supporting_data: dict
    detected_at: datetime
    period_start: date
    period_end: date
    status: str
    claude_model_used: str | None = None
    claude_input_tokens: int | None = None
    claude_output_tokens: int | None = None


class InsightListResponse(BaseModel):
    items: list[InsightResponse]
    total: int


class InsightStatusUpdate(BaseModel):
    status: str  # 'acknowledged' | 'dismissed'


class InsightGenerateResponse(BaseModel):
    created: int
    by_kind: dict[str, int] = {}  # e.g. {"anomaly": 2, "decay": 1, "opportunity": 1, ...}
