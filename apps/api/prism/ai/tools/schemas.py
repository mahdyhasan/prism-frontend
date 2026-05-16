from __future__ import annotations

from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, Field


class DateRangeInput(BaseModel):
    start: str = Field(..., description="Start date in YYYY-MM-DD format")
    end: str = Field(..., description="End date in YYYY-MM-DD format")


class QueryGA4Input(BaseModel):
    property_id: int
    date_range: DateRangeInput
    metrics: list[str] = Field(..., description="GA4 metric names, e.g. sessions, totalUsers, conversions")
    dimensions: list[str] | None = Field(None, description="GA4 dimension names, e.g. date, landingPage, deviceCategory")
    filters: dict[str, Any] | None = None
    limit: int = Field(200, ge=1, le=1000)
    sort_by: str | None = None  # metric name to sort desc


class QueryGSCInput(BaseModel):
    property_id: int
    date_range: DateRangeInput
    dimensions: list[str] = Field(default=["date"], description="e.g. date, page, query")
    filters: dict[str, Any] | None = None
    limit: int = Field(200, ge=1, le=1000)
    sort_by: str | None = None  # clicks or impressions


class ComparePeriodsInput(BaseModel):
    property_id: int
    source: Literal["ga4", "gsc"]
    metric: str
    period_a: DateRangeInput
    period_b: DateRangeInput
    dimensions: list[str] | None = None
    filters: dict[str, Any] | None = None


class CorrelatePageInput(BaseModel):
    property_id: int
    page_pattern: str = Field(..., description="Exact path like /staff-augmentation or prefix like /blog/")
    date_range: DateRangeInput


class IntentVsOutcomeInput(BaseModel):
    property_id: int
    date_range: DateRangeInput
    min_impression_delta_pct: float = Field(20.0, description="Min % impression change to be flagged")


class VanityVsValueInput(BaseModel):
    property_id: int
    date_range: DateRangeInput
    limit: int = 50


class CannibalizationInput(BaseModel):
    property_id: int
    date_range: DateRangeInput
    impression_threshold: int = Field(100, description="Min impressions per day for a query to be checked")


class SerpOpportunityInput(BaseModel):
    property_id: int
    min_position: float = Field(8.0, description="Min position (default 8, worse than this)")
    max_position: float = Field(20.0, description="Max position (default 20)")
    min_impressions: int = Field(50, description="Min daily impressions to qualify")


class ContentDecayInput(BaseModel):
    property_id: int
    lookback_days: int = Field(90, description="Days to look back for decay detection")
    min_sessions_threshold: int = Field(10, description="Min sessions/day to be tracked")


class DetectAnomaliesInput(BaseModel):
    property_id: int
    source: Literal["ga4", "gsc"]
    metric: str = Field(..., description="e.g. sessions for GA4, clicks for GSC")
    lookback_days: int = Field(30, ge=14, le=180)
    z_threshold: float = Field(2.5, description="Z-score threshold for anomaly detection")


class RollingTrendInput(BaseModel):
    property_id: int
    source: Literal["ga4", "gsc"]
    metric: str
    window_days: int = Field(7, ge=3, le=30)
    lookback_days: int = Field(90, ge=14, le=365)


class SegmentSplitInput(BaseModel):
    property_id: int
    source: Literal["ga4", "gsc"]
    metric: str
    dimension: str
    date_range: DateRangeInput


class RecallMemoryInput(BaseModel):
    property_id: int
    query: str = Field(..., description="What to search for in memory")
    limit: int = Field(8, ge=1, le=20)


class SaveMemoryInput(BaseModel):
    property_id: int
    kind: Literal["goal", "decision", "hypothesis", "business_context", "preference", "recurring_concern"]
    text: str
    tags: list[str] = Field(default_factory=list)
    confidence: Literal["explicit", "implied"] = "explicit"
    supersedes_memory_id: int | None = None
    expires_after_days: int | None = None


class ListPinnedInput(BaseModel):
    property_id: int


class GetPropertyMetaInput(BaseModel):
    property_id: int


# ── CWV tool schemas ──────────────────────────────────────────────────────────

class GetPageCWVInput(BaseModel):
    property_id: int
    url: str
    strategy: str = "mobile"


class GetOriginCWVInput(BaseModel):
    property_id: int
    strategy: str = "mobile"


class ScanCWVProblemsInput(BaseModel):
    property_id: int
    strategy: str = "mobile"
    status_filter: list[str] = ["poor", "needs_improvement"]
    limit: int = 20


class CWVMobileDesktopInput(BaseModel):
    property_id: int
    limit: int = 20


class CWVTrendInput(BaseModel):
    property_id: int
    url: str
    strategy: str = "mobile"
    days: int = 30


# ── Action tool schemas ───────────────────────────────────────────────────────

class GSCSubmitSitemapInput(BaseModel):
    property_id: int
    sitemap_url: str


class GSCDeleteSitemapInput(BaseModel):
    property_id: int
    sitemap_url: str


class GSCInspectURLInput(BaseModel):
    property_id: int
    url: str


class RunPSIAuditInput(BaseModel):
    property_id: int
    url: str
    strategy: str = "mobile"
