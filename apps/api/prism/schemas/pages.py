from __future__ import annotations

from pydantic import BaseModel


class PageRow(BaseModel):
    page: str
    # GA4
    sessions: int
    users: int
    engaged_sessions: int
    conversions: int
    revenue: float
    bounce_rate: float
    engagement_rate: float | None = None
    conversion_rate: float | None = None
    avg_session_duration: float
    exits: int = 0
    exit_rate: float | None = None
    # GSC (always zero when device filter is active)
    clicks: int
    impressions: int
    ctr: float
    avg_position: float
    # Microsoft Clarity (null when no token / data not yet available)
    frustration_score: float | None = None  # (dead + 2*rage + quick_back) / sessions, [0..1]
    scroll_depth_avg: float | None = None   # 0.0–1.0
    # Composite
    health_score: float | None = None  # None when sessions < health-floor


class PagePerformanceResponse(BaseModel):
    start_date: str
    end_date: str
    rows: list[PageRow]
    total_rows: int  # before LIMIT, for "showing X of Y" UI hint
    device: str | None = None  # echoes the filter that was applied (or null)
