from __future__ import annotations

import asyncio
from datetime import date, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.ga4 import (
    GA4ChannelsDaily,
    GA4DailyMetrics,
    GA4DevicesDaily,
    GA4EventsDaily,
    GA4HourlyMetrics,
    GA4LandingPagesDaily,
    GA4TrafficSourcesDaily,
    GA4UserTypeDaily,
)
from prism.db.models.sync import SyncJob
from prism.schemas.overview import (
    DailyPoint,
    DeviceRow,
    KPIValue,
    LandingPageRow,
    OverviewKPIs,
    OverviewResponse,
    PrimaryEventConversion,
    TrafficSourceRow,
)


def _delta(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def _kpi(current: float, previous: float | None) -> KPIValue:
    return KPIValue(value=current, previous_value=previous, delta_percent=_delta(current, previous))


def _conv_rate(conversions: int | float, sessions: int | float) -> float | None:
    """Conversions / sessions. None when sessions == 0 (avoid NaN-flavoured KPIs)."""
    s = float(sessions or 0)
    if s <= 0:
        return None
    return round(float(conversions or 0) / s, 6)


def _parse_preset(preset: str) -> tuple[date, date]:
    today = date.today()
    presets = {
        "last_7d": (today - timedelta(days=7), today - timedelta(days=1)),
        "last_30d": (today - timedelta(days=30), today - timedelta(days=1)),
        "last_90d": (today - timedelta(days=90), today - timedelta(days=1)),
        "last_12m": (today - timedelta(days=365), today - timedelta(days=1)),
        "last_14m": (today - timedelta(days=420), today - timedelta(days=1)),
    }
    if preset not in presets:
        msg = f"Unknown preset: {preset}. Valid: {list(presets)}"
        raise ValueError(msg)
    return presets[preset]


def resolve_date_range(
    start_date: str | None,
    end_date: str | None,
    preset: str | None,
) -> tuple[date, date]:
    if preset:
        return _parse_preset(preset)
    if start_date and end_date:
        return date.fromisoformat(start_date), date.fromisoformat(end_date)
    return _parse_preset("last_30d")


def compare_period(start: date, end: date, compare_to: str) -> tuple[date, date]:
    delta = (end - start).days + 1
    if compare_to == "previous_period":
        cend = start - timedelta(days=1)
        cstart = cend - timedelta(days=delta - 1)
        return cstart, cend
    if compare_to == "same_period_last_year":
        return start - timedelta(days=365), end - timedelta(days=365)
    msg = f"Unknown compare_to: {compare_to}"
    raise ValueError(msg)


async def _aggregate_metrics(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> dict:
    result = await db.execute(
        select(
            func.coalesce(func.sum(GA4DailyMetrics.sessions), 0).label("sessions"),
            func.coalesce(func.sum(GA4DailyMetrics.users), 0).label("users"),
            func.coalesce(func.sum(GA4DailyMetrics.new_users), 0).label("new_users"),
            func.coalesce(func.avg(GA4DailyMetrics.engagement_rate), 0).label("engagement_rate"),
            func.coalesce(func.avg(GA4DailyMetrics.bounce_rate), 0).label("bounce_rate"),
            func.coalesce(func.sum(GA4DailyMetrics.conversions), 0).label("conversions"),
            func.coalesce(func.sum(GA4DailyMetrics.total_revenue), 0).label("total_revenue"),
        ).where(
            GA4DailyMetrics.property_id == property_id,
            GA4DailyMetrics.date >= start,
            GA4DailyMetrics.date <= end,
            GA4DailyMetrics.dimension_hash == "base",
        )
    )
    row = result.one()
    return {
        "sessions": float(row.sessions),
        "users": float(row.users),
        "new_users": float(row.new_users),
        "engagement_rate": float(row.engagement_rate),
        "bounce_rate": float(row.bounce_rate),
        "conversions": float(row.conversions),
        "total_revenue": float(row.total_revenue),
    }


async def _get_event_conversion_counts(
    db: AsyncSession,
    property_id: int,
    event_names: list[str],
    start: date,
    end: date,
) -> dict[str, int]:
    """Sum conversion-event occurrences per event name from ga4_events_daily."""
    if not event_names:
        return {}
    result = await db.execute(
        select(
            GA4EventsDaily.event_name,
            func.coalesce(func.sum(GA4EventsDaily.event_count), 0).label("count"),
        )
        .where(
            GA4EventsDaily.property_id == property_id,
            GA4EventsDaily.date >= start,
            GA4EventsDaily.date <= end,
            GA4EventsDaily.event_name.in_(event_names),
        )
        .group_by(GA4EventsDaily.event_name)
    )
    return {row.event_name: int(row.count or 0) for row in result.all()}


async def _get_sessions_trend(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> list[DailyPoint]:
    result = await db.execute(
        select(
            GA4DailyMetrics.date,
            func.sum(GA4DailyMetrics.sessions).label("sessions"),
            func.sum(GA4DailyMetrics.users).label("users"),
        ).where(
            GA4DailyMetrics.property_id == property_id,
            GA4DailyMetrics.date >= start,
            GA4DailyMetrics.date <= end,
            GA4DailyMetrics.dimension_hash == "base",
        ).group_by(GA4DailyMetrics.date).order_by(GA4DailyMetrics.date)
    )
    return [DailyPoint(date=row.date.isoformat(), sessions=row.sessions, users=row.users)
            for row in result.all()]


async def _get_top_landing_pages(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
    limit: int = 10,
) -> list[LandingPageRow]:
    result = await db.execute(
        select(
            GA4LandingPagesDaily.landing_page,
            func.sum(GA4LandingPagesDaily.sessions).label("sessions"),
            func.sum(GA4LandingPagesDaily.users).label("users"),
            func.sum(GA4LandingPagesDaily.conversions).label("conversions"),
            func.avg(GA4LandingPagesDaily.bounce_rate).label("bounce_rate"),
        ).where(
            GA4LandingPagesDaily.property_id == property_id,
            GA4LandingPagesDaily.date >= start,
            GA4LandingPagesDaily.date <= end,
        ).group_by(GA4LandingPagesDaily.landing_page)
        .order_by(text("sessions DESC"))
        .limit(limit)
    )
    return [
        LandingPageRow(
            landing_page=row.landing_page,
            sessions=row.sessions,
            users=row.users,
            conversions=row.conversions,
            conversion_rate=_conv_rate(row.conversions, row.sessions),
            bounce_rate=round(float(row.bounce_rate), 4),
        )
        for row in result.all()
    ]


async def _get_top_traffic_sources(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
    limit: int = 10,
) -> list[TrafficSourceRow]:
    result = await db.execute(
        select(
            GA4TrafficSourcesDaily.source,
            GA4TrafficSourcesDaily.medium,
            func.sum(GA4TrafficSourcesDaily.sessions).label("sessions"),
            func.sum(GA4TrafficSourcesDaily.users).label("users"),
            func.sum(GA4TrafficSourcesDaily.conversions).label("conversions"),
        ).where(
            GA4TrafficSourcesDaily.property_id == property_id,
            GA4TrafficSourcesDaily.date >= start,
            GA4TrafficSourcesDaily.date <= end,
        ).group_by(GA4TrafficSourcesDaily.source, GA4TrafficSourcesDaily.medium)
        .order_by(text("sessions DESC"))
        .limit(limit)
    )
    return [
        TrafficSourceRow(
            source=row.source,
            medium=row.medium,
            sessions=row.sessions,
            users=row.users,
            conversions=row.conversions,
            conversion_rate=_conv_rate(row.conversions, row.sessions),
        )
        for row in result.all()
    ]


async def _get_devices(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> list[DeviceRow]:
    result = await db.execute(
        select(
            GA4DevicesDaily.device_category,
            func.sum(GA4DevicesDaily.sessions).label("sessions"),
            func.sum(GA4DevicesDaily.users).label("users"),
            func.sum(GA4DevicesDaily.conversions).label("conversions"),
        ).where(
            GA4DevicesDaily.property_id == property_id,
            GA4DevicesDaily.date >= start,
            GA4DevicesDaily.date <= end,
        ).group_by(GA4DevicesDaily.device_category)
        .order_by(text("sessions DESC"))
    )
    return [
        DeviceRow(
            device_category=row.device_category,
            sessions=row.sessions,
            users=row.users,
            conversions=row.conversions,
            conversion_rate=_conv_rate(row.conversions, row.sessions),
        )
        for row in result.all()
    ]


async def get_overview(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
    compare_to: str | None = None,
    primary_conversion_events: list[str] | None = None,
) -> OverviewResponse:
    current, compare = await _aggregate_metrics(db, property_id, start, end), None
    compare_range: tuple[date, date] | None = None

    if compare_to:
        cstart, cend = compare_period(start, end, compare_to)
        compare_range = (cstart, cend)
        compare = await _aggregate_metrics(db, property_id, cstart, cend)

    # Primary-event conversions: fetch counts for the configured event names,
    # plus the same counts in the compare period if requested.
    primary_events_out: list[PrimaryEventConversion] = []
    if primary_conversion_events:
        current_counts = await _get_event_conversion_counts(
            db, property_id, primary_conversion_events, start, end,
        )
        compare_counts: dict[str, int] = {}
        if compare_range:
            compare_counts = await _get_event_conversion_counts(
                db, property_id, primary_conversion_events, compare_range[0], compare_range[1],
            )
        current_sessions = float(current["sessions"]) or 0.0
        compare_sessions = float(compare["sessions"]) if compare else 0.0
        for event_name in primary_conversion_events:
            cur_n = current_counts.get(event_name, 0)
            prev_n = compare_counts.get(event_name) if compare_range else None
            rate = _conv_rate(cur_n, current_sessions) or 0.0
            prev_rate = (
                _conv_rate(prev_n, compare_sessions) if prev_n is not None else None
            )
            primary_events_out.append(
                PrimaryEventConversion(
                    event_name=event_name,
                    count=cur_n,
                    rate_per_session=rate,
                    delta_count_percent=_delta(cur_n, prev_n),
                    delta_rate_percent=_delta(rate, prev_rate),
                ),
            )

    kpis = OverviewKPIs(
        sessions=_kpi(current["sessions"], compare["sessions"] if compare else None),
        users=_kpi(current["users"], compare["users"] if compare else None),
        new_users=_kpi(current["new_users"], compare["new_users"] if compare else None),
        engagement_rate=_kpi(current["engagement_rate"], compare["engagement_rate"] if compare else None),
        bounce_rate=_kpi(current["bounce_rate"], compare["bounce_rate"] if compare else None),
        conversions=_kpi(current["conversions"], compare["conversions"] if compare else None),
        total_revenue=_kpi(current["total_revenue"], compare["total_revenue"] if compare else None),
        primary_event_conversions=primary_events_out,
    )

    trend, pages, sources, devices = await asyncio.gather(
        _get_sessions_trend(db, property_id, start, end),
        _get_top_landing_pages(db, property_id, start, end),
        _get_top_traffic_sources(db, property_id, start, end),
        _get_devices(db, property_id, start, end),
    )

    # Last sync time
    sync_result = await db.execute(
        select(SyncJob.finished_at)
        .where(SyncJob.property_id == property_id, SyncJob.source == "ga4", SyncJob.status == "done")
        .order_by(SyncJob.finished_at.desc())
        .limit(1)
    )
    last_sync = sync_result.scalar_one_or_none()

    return OverviewResponse(
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        compare_start_date=compare_range[0].isoformat() if compare_range else None,
        compare_end_date=compare_range[1].isoformat() if compare_range else None,
        kpis=kpis,
        sessions_trend=trend,
        top_landing_pages=pages,
        top_traffic_sources=sources,
        devices=devices,
        last_synced_at=last_sync.isoformat() if last_sync else None,
    )


# ── Tier 1 dimension reads ──────────────────────────────────────────────────


async def get_channel_breakdown(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> list[dict]:
    """Aggregate sessions/users/conversions/revenue per channel group with share of sessions."""
    result = await db.execute(
        select(
            GA4ChannelsDaily.channel_group,
            func.coalesce(func.sum(GA4ChannelsDaily.sessions), 0).label("sessions"),
            func.coalesce(func.sum(GA4ChannelsDaily.users), 0).label("users"),
            func.coalesce(func.sum(GA4ChannelsDaily.conversions), 0).label("conversions"),
            func.coalesce(func.sum(GA4ChannelsDaily.total_revenue), 0).label("revenue"),
        )
        .where(
            GA4ChannelsDaily.property_id == property_id,
            GA4ChannelsDaily.date >= start,
            GA4ChannelsDaily.date <= end,
        )
        .group_by(GA4ChannelsDaily.channel_group)
        .order_by(text("sessions DESC"))
    )
    raw = [
        {
            "channel_group": r.channel_group,
            "sessions": int(r.sessions or 0),
            "users": int(r.users or 0),
            "conversions": int(r.conversions or 0),
            "conversion_rate": _conv_rate(r.conversions, r.sessions),
            "revenue": float(r.revenue or 0),
        }
        for r in result.all()
    ]
    total_sessions = sum(row["sessions"] for row in raw)
    for row in raw:
        row["share"] = round(row["sessions"] / total_sessions, 6) if total_sessions else 0.0
    return raw


async def get_hourly_heatmap(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> list[dict]:
    """Return a 7×24 grid: day_of_week (0=Mon..6=Sun) × hour (0-23) with sessions/users.

    DAYOFWEEK in MySQL returns 1=Sun..7=Sat — normalize to 0=Mon..6=Sun in Python.
    """
    result = await db.execute(
        select(
            GA4HourlyMetrics.date,
            GA4HourlyMetrics.hour,
            func.coalesce(func.sum(GA4HourlyMetrics.sessions), 0).label("sessions"),
            func.coalesce(func.sum(GA4HourlyMetrics.users), 0).label("users"),
        )
        .where(
            GA4HourlyMetrics.property_id == property_id,
            GA4HourlyMetrics.date >= start,
            GA4HourlyMetrics.date <= end,
        )
        .group_by(GA4HourlyMetrics.date, GA4HourlyMetrics.hour)
    )

    grid: dict[tuple[int, int], dict] = {}
    for r in result.all():
        # Python weekday(): 0=Mon..6=Sun
        dow = r.date.weekday()
        hr = int(r.hour or 0)
        key = (dow, hr)
        cell = grid.setdefault(key, {"day_of_week": dow, "hour": hr, "sessions": 0, "users": 0})
        cell["sessions"] += int(r.sessions or 0)
        cell["users"] += int(r.users or 0)

    # Fill missing cells with zeros for a complete 7×24 grid
    out: list[dict] = []
    for dow in range(7):
        for hr in range(24):
            cell = grid.get((dow, hr), {"day_of_week": dow, "hour": hr, "sessions": 0, "users": 0})
            out.append(cell)
    return out


async def get_user_type_split(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> dict:
    """Return aggregated metrics for new vs returning users plus total."""
    result = await db.execute(
        select(
            GA4UserTypeDaily.user_type,
            func.coalesce(func.sum(GA4UserTypeDaily.sessions), 0).label("sessions"),
            func.coalesce(func.sum(GA4UserTypeDaily.users), 0).label("users"),
            func.coalesce(func.sum(GA4UserTypeDaily.engaged_sessions), 0).label("engaged_sessions"),
        )
        .where(
            GA4UserTypeDaily.property_id == property_id,
            GA4UserTypeDaily.date >= start,
            GA4UserTypeDaily.date <= end,
        )
        .group_by(GA4UserTypeDaily.user_type)
    )

    new_b = {"sessions": 0, "users": 0, "engaged_sessions": 0}
    returning_b = {"sessions": 0, "users": 0, "engaged_sessions": 0}
    other_b = {"sessions": 0, "users": 0, "engaged_sessions": 0}

    for r in result.all():
        bucket = {
            "sessions": int(r.sessions or 0),
            "users": int(r.users or 0),
            "engaged_sessions": int(r.engaged_sessions or 0),
        }
        ut = (r.user_type or "").lower()
        if ut == "new":
            new_b = bucket
        elif ut == "returning":
            returning_b = bucket
        else:
            for k, v in bucket.items():
                other_b[k] += v

    total = {
        "sessions": new_b["sessions"] + returning_b["sessions"] + other_b["sessions"],
        "users": new_b["users"] + returning_b["users"] + other_b["users"],
        "engaged_sessions": new_b["engaged_sessions"] + returning_b["engaged_sessions"] + other_b["engaged_sessions"],
    }
    return {
        "new": new_b,
        "returning": returning_b,
        "total": total,
    }
