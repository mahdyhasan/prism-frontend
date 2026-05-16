from __future__ import annotations

from datetime import date

from sqlalchemy import case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.gsc import (
    GSCAppearanceDaily,
    GSCPagesDaily,
    GSCQueriesDaily,
    GSCSearchTypeDaily,
)


def _delta(current: float, previous: float | None) -> float | None:
    if previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


async def _aggregate_kpis(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> dict:
    """Aggregate clicks, impressions, ctr, position across the queries table.

    CTR is computed as total_clicks / total_impressions (not avg of daily ctr,
    which would be misleading). Position is impression-weighted average.
    """
    impressions_sum = func.coalesce(func.sum(GSCQueriesDaily.impressions), 0)
    clicks_sum = func.coalesce(func.sum(GSCQueriesDaily.clicks), 0)
    weighted_position = func.coalesce(
        func.sum(GSCQueriesDaily.position * GSCQueriesDaily.impressions),
        0.0,
    )

    result = await db.execute(
        select(
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        ).where(
            GSCQueriesDaily.property_id == property_id,
            GSCQueriesDaily.date >= start,
            GSCQueriesDaily.date <= end,
        )
    )
    row = result.one()
    clicks = float(row.clicks or 0)
    impressions = float(row.impressions or 0)
    avg_position = float(row.weighted_position or 0) / impressions if impressions else 0.0
    ctr = clicks / impressions if impressions else 0.0
    return {
        "clicks": clicks,
        "impressions": impressions,
        "ctr": ctr,
        "avg_position": avg_position,
    }


async def get_search_kpis(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
    compare_start: date | None = None,
    compare_end: date | None = None,
) -> dict:
    """Return flat KPI dict matching the SearchKPIs Pydantic schema."""
    current = await _aggregate_kpis(db, property_id, start, end)
    compare = None
    if compare_start and compare_end:
        compare = await _aggregate_kpis(db, property_id, compare_start, compare_end)

    def delta(key: str) -> float | None:
        return _delta(current[key], compare[key] if compare else None)

    return {
        "clicks": int(current["clicks"]),
        "impressions": int(current["impressions"]),
        "ctr": round(current["ctr"], 6),
        "avg_position": round(current["avg_position"], 2),
        "clicks_delta": delta("clicks"),
        "impressions_delta": delta("impressions"),
        "ctr_delta": delta("ctr"),
        "position_delta": delta("avg_position"),
    }


async def get_daily_trend(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> list[dict]:
    """Daily clicks/impressions/CTR/position for the trend chart."""
    impressions_sum = func.coalesce(func.sum(GSCQueriesDaily.impressions), 0)
    clicks_sum = func.coalesce(func.sum(GSCQueriesDaily.clicks), 0)
    weighted_position = func.coalesce(
        func.sum(GSCQueriesDaily.position * GSCQueriesDaily.impressions),
        0.0,
    )

    result = await db.execute(
        select(
            GSCQueriesDaily.date.label("date"),
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        )
        .where(
            GSCQueriesDaily.property_id == property_id,
            GSCQueriesDaily.date >= start,
            GSCQueriesDaily.date <= end,
        )
        .group_by(GSCQueriesDaily.date)
        .order_by(GSCQueriesDaily.date)
    )

    rows: list[dict] = []
    for r in result.all():
        clicks = float(r.clicks or 0)
        impressions = float(r.impressions or 0)
        ctr = clicks / impressions if impressions else 0.0
        avg_position = float(r.weighted_position or 0) / impressions if impressions else 0.0
        rows.append({
            "date": r.date.isoformat(),
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": round(ctr, 6),
            "position": round(avg_position, 2),
        })
    return rows


async def get_top_queries(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
    limit: int = 50,
) -> list[dict]:
    impressions_sum = func.sum(GSCQueriesDaily.impressions)
    clicks_sum = func.sum(GSCQueriesDaily.clicks)
    weighted_position = func.sum(GSCQueriesDaily.position * GSCQueriesDaily.impressions)

    result = await db.execute(
        select(
            GSCQueriesDaily.query.label("query"),
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        )
        .where(
            GSCQueriesDaily.property_id == property_id,
            GSCQueriesDaily.date >= start,
            GSCQueriesDaily.date <= end,
        )
        .group_by(GSCQueriesDaily.query)
        .order_by(text("clicks DESC"))
        .limit(limit)
    )

    rows: list[dict] = []
    for r in result.all():
        clicks = float(r.clicks or 0)
        impressions = float(r.impressions or 0)
        ctr = clicks / impressions if impressions else 0.0
        avg_position = float(r.weighted_position or 0) / impressions if impressions else 0.0
        rows.append({
            "query": r.query,
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": round(ctr, 6),
            "position": round(avg_position, 2),
        })
    return rows


async def get_top_pages(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
    limit: int = 50,
) -> list[dict]:
    impressions_sum = func.sum(GSCPagesDaily.impressions)
    clicks_sum = func.sum(GSCPagesDaily.clicks)
    weighted_position = func.sum(GSCPagesDaily.position * GSCPagesDaily.impressions)

    result = await db.execute(
        select(
            GSCPagesDaily.page.label("page"),
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        )
        .where(
            GSCPagesDaily.property_id == property_id,
            GSCPagesDaily.date >= start,
            GSCPagesDaily.date <= end,
        )
        .group_by(GSCPagesDaily.page)
        .order_by(text("clicks DESC"))
        .limit(limit)
    )

    rows: list[dict] = []
    for r in result.all():
        clicks = float(r.clicks or 0)
        impressions = float(r.impressions or 0)
        ctr = clicks / impressions if impressions else 0.0
        avg_position = float(r.weighted_position or 0) / impressions if impressions else 0.0
        rows.append({
            "page": r.page,
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": round(ctr, 6),
            "position": round(avg_position, 2),
        })
    return rows


async def get_opportunities(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
    limit: int = 20,
) -> list[dict]:
    """Queries ranking position 5-20 with decent impressions — rank-improvement candidates."""
    impressions_sum = func.sum(GSCQueriesDaily.impressions)
    clicks_sum = func.sum(GSCQueriesDaily.clicks)
    weighted_position = func.sum(GSCQueriesDaily.position * GSCQueriesDaily.impressions)

    # We compute per-query weighted position in HAVING via the same expression.
    # Use a subquery so we can filter the avg position cleanly.
    inner = (
        select(
            GSCQueriesDaily.query.label("query"),
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        )
        .where(
            GSCQueriesDaily.property_id == property_id,
            GSCQueriesDaily.date >= start,
            GSCQueriesDaily.date <= end,
        )
        .group_by(GSCQueriesDaily.query)
        .having(impressions_sum >= 50)
        .subquery()
    )

    avg_position_expr = case(
        (inner.c.impressions > 0, inner.c.weighted_position / inner.c.impressions),
        else_=0.0,
    )

    result = await db.execute(
        select(
            inner.c.query,
            inner.c.clicks,
            inner.c.impressions,
            avg_position_expr.label("avg_position"),
        )
        .where(avg_position_expr >= 5.0, avg_position_expr <= 20.0)
        .order_by(text("impressions DESC"))
        .limit(limit)
    )

    rows: list[dict] = []
    for r in result.all():
        clicks = float(r.clicks or 0)
        impressions = float(r.impressions or 0)
        ctr = clicks / impressions if impressions else 0.0
        rows.append({
            "query": r.query,
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": round(ctr, 6),
            "position": round(float(r.avg_position or 0), 2),
        })
    return rows


# ── Tier 1 dimension reads ──────────────────────────────────────────────────


async def get_appearance_breakdown(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> list[dict]:
    """Aggregate clicks/impressions/ctr/position by searchAppearance type."""
    impressions_sum = func.sum(GSCAppearanceDaily.impressions)
    clicks_sum = func.sum(GSCAppearanceDaily.clicks)
    weighted_position = func.sum(GSCAppearanceDaily.position * GSCAppearanceDaily.impressions)

    result = await db.execute(
        select(
            GSCAppearanceDaily.search_appearance.label("search_appearance"),
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        )
        .where(
            GSCAppearanceDaily.property_id == property_id,
            GSCAppearanceDaily.date >= start,
            GSCAppearanceDaily.date <= end,
        )
        .group_by(GSCAppearanceDaily.search_appearance)
        .order_by(text("clicks DESC"))
    )

    rows: list[dict] = []
    for r in result.all():
        clicks = float(r.clicks or 0)
        impressions = float(r.impressions or 0)
        ctr = clicks / impressions if impressions else 0.0
        avg_position = float(r.weighted_position or 0) / impressions if impressions else 0.0
        rows.append({
            "search_appearance": r.search_appearance,
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": round(ctr, 6),
            "position": round(avg_position, 2),
        })
    return rows


async def get_search_type_breakdown(
    db: AsyncSession,
    property_id: int,
    start: date,
    end: date,
) -> list[dict]:
    """Aggregate clicks/impressions/ctr/position by GSC search type (web, image, video, ...)."""
    impressions_sum = func.sum(GSCSearchTypeDaily.impressions)
    clicks_sum = func.sum(GSCSearchTypeDaily.clicks)
    weighted_position = func.sum(GSCSearchTypeDaily.position * GSCSearchTypeDaily.impressions)

    result = await db.execute(
        select(
            GSCSearchTypeDaily.search_type.label("search_type"),
            clicks_sum.label("clicks"),
            impressions_sum.label("impressions"),
            weighted_position.label("weighted_position"),
        )
        .where(
            GSCSearchTypeDaily.property_id == property_id,
            GSCSearchTypeDaily.date >= start,
            GSCSearchTypeDaily.date <= end,
        )
        .group_by(GSCSearchTypeDaily.search_type)
        .order_by(text("clicks DESC"))
    )

    rows: list[dict] = []
    for r in result.all():
        clicks = float(r.clicks or 0)
        impressions = float(r.impressions or 0)
        ctr = clicks / impressions if impressions else 0.0
        avg_position = float(r.weighted_position or 0) / impressions if impressions else 0.0
        rows.append({
            "search_type": r.search_type,
            "clicks": int(clicks),
            "impressions": int(impressions),
            "ctr": round(ctr, 6),
            "position": round(avg_position, 2),
        })
    return rows
