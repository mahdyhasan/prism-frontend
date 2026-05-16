from __future__ import annotations

from pydantic import BaseModel


# Flat KPI shape — matches the TypeScript SearchKPIs interface directly.
class SearchKPIs(BaseModel):
    clicks: int
    impressions: int
    ctr: float
    avg_position: float
    clicks_delta: float | None = None
    impressions_delta: float | None = None
    ctr_delta: float | None = None
    position_delta: float | None = None


class SearchDailyPoint(BaseModel):
    date: str
    clicks: int
    impressions: int
    ctr: float
    position: float  # named "position" to match the frontend SearchDailyPoint type


class SearchQuery(BaseModel):
    query: str
    clicks: int
    impressions: int
    ctr: float
    position: float


class SearchPage(BaseModel):
    page: str
    clicks: int
    impressions: int
    ctr: float
    position: float


class SearchOpportunity(BaseModel):
    query: str
    page: str = ""  # best-match page from GSCPagesDaily; empty when unknown
    clicks: int
    impressions: int
    ctr: float
    position: float


class SearchOverviewResponse(BaseModel):
    start_date: str
    end_date: str
    compare_start_date: str | None = None
    compare_end_date: str | None = None
    kpis: SearchKPIs
    daily_trend: list[SearchDailyPoint] = []
    top_queries: list[SearchQuery] = []
    top_pages: list[SearchPage] = []
    opportunities: list[SearchOpportunity] = []
    last_synced_at: str | None = None


class LinkGSCRequest(BaseModel):
    site_url: str  # e.g. "sc-domain:example.com" or "https://example.com/"


# ── Tier 1 dimension schemas ────────────────────────────────────────────────


class AppearanceBreakdownItem(BaseModel):
    search_appearance: str
    clicks: int
    impressions: int
    ctr: float
    position: float


class SearchTypeBreakdownItem(BaseModel):
    search_type: str
    clicks: int
    impressions: int
    ctr: float
    position: float
