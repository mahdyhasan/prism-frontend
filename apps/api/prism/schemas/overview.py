from __future__ import annotations

from pydantic import BaseModel


class KPIValue(BaseModel):
    value: float
    previous_value: float | None = None
    delta_percent: float | None = None


class PrimaryEventConversion(BaseModel):
    """Conversion-rate KPI for a single primary event.

    `rate_per_session = conversions / sessions` (0 if no sessions).
    """
    event_name: str
    count: int
    rate_per_session: float
    delta_count_percent: float | None = None     # %-change vs compare period (count)
    delta_rate_percent: float | None = None      # %-change vs compare period (rate)


class OverviewKPIs(BaseModel):
    sessions: KPIValue
    users: KPIValue
    new_users: KPIValue
    engagement_rate: KPIValue
    bounce_rate: KPIValue
    conversions: KPIValue
    total_revenue: KPIValue
    primary_event_conversions: list[PrimaryEventConversion] = []


class DailyPoint(BaseModel):
    date: str       # ISO date string YYYY-MM-DD
    sessions: int
    users: int


class LandingPageRow(BaseModel):
    landing_page: str
    sessions: int
    users: int
    conversions: int
    conversion_rate: float | None = None  # conversions / sessions
    bounce_rate: float


class TrafficSourceRow(BaseModel):
    source: str
    medium: str
    sessions: int
    users: int
    conversions: int
    conversion_rate: float | None = None


class DeviceRow(BaseModel):
    device_category: str
    sessions: int
    users: int
    conversions: int
    conversion_rate: float | None = None


class OverviewResponse(BaseModel):
    start_date: str
    end_date: str
    compare_start_date: str | None = None
    compare_end_date: str | None = None
    kpis: OverviewKPIs
    sessions_trend: list[DailyPoint]
    top_landing_pages: list[LandingPageRow]
    top_traffic_sources: list[TrafficSourceRow]
    devices: list[DeviceRow]
    last_synced_at: str | None = None


# ── Tier 1 dimension schemas ────────────────────────────────────────────────


class ChannelBreakdownItem(BaseModel):
    channel_group: str
    sessions: int
    users: int
    conversions: int
    conversion_rate: float | None = None
    revenue: float
    share: float


class HourlyHeatmapPoint(BaseModel):
    day_of_week: int  # 0=Mon..6=Sun
    hour: int         # 0..23
    sessions: int
    users: int


class UserTypeBucket(BaseModel):
    sessions: int
    users: int
    engaged_sessions: int


class UserTypeSplit(BaseModel):
    new: UserTypeBucket
    returning: UserTypeBucket
    total: UserTypeBucket
