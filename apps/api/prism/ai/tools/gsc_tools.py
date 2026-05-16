from __future__ import annotations

from datetime import date
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.gsc import (
    GSCAppearanceDaily,
    GSCPagesDaily,
    GSCQueriesDaily,
    GSCQueryPageDaily,
    GSCSearchTypeDaily,
)
from prism.ai.tools.schemas import QueryGSCInput


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _parse_date(d: str) -> date:
    return date.fromisoformat(d)


def _compute_tail_summary(all_values: list[float]) -> dict[str, Any]:
    if not all_values:
        return {"row_count": 0, "sum": 0.0, "mean": 0.0, "p50": 0.0}
    sorted_vals = sorted(all_values)
    n = len(sorted_vals)
    total = sum(sorted_vals)
    mean = total / n
    mid = n // 2
    p50 = sorted_vals[mid] if n % 2 == 1 else (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
    return {"row_count": n, "sum": round(total, 4), "mean": round(mean, 4), "p50": round(p50, 4)}


def _apply_cap_and_sort(
    rows: list[dict[str, Any]],
    primary_col: str,
    limit: int,
    sort_by: str | None,
    table: str,
    inp: QueryGSCInput,
) -> dict[str, Any]:
    sort_col = sort_by or primary_col

    def sort_key(r: dict[str, Any]) -> float:
        v = r.get(sort_col, 0)
        try:
            return float(v) if v is not None else 0.0
        except (TypeError, ValueError):
            return 0.0

    rows.sort(key=sort_key, reverse=True)
    total = len(rows)
    truncated = total > limit
    tail_summary: dict[str, Any] | None = None

    if truncated:
        tail_rows = rows[limit:]
        tail_vals = [sort_key(r) for r in tail_rows]
        tail_summary = _compute_tail_summary(tail_vals)
        rows = rows[:limit]

    return {
        "rows": rows,
        "truncated": truncated,
        "tail_summary": tail_summary,
        "row_count": total,
        "query_info": {
            "table": table,
            "date_range": {"start": inp.date_range.start, "end": inp.date_range.end},
            "dimensions": inp.dimensions,
        },
    }


# ---------------------------------------------------------------------------
# query_gsc
# ---------------------------------------------------------------------------

async def query_gsc(inp: QueryGSCInput, db: AsyncSession) -> dict[str, Any]:
    start = _parse_date(inp.date_range.start)
    end = _parse_date(inp.date_range.end)
    dims = list(inp.dimensions) if inp.dimensions else ["date"]

    dim_set = set(dims)

    if dim_set == {"date"}:
        return await _query_by_date(inp, db, start, end)
    elif dim_set == {"query"}:
        return await _query_by_query(inp, db, start, end)
    elif dim_set == {"page"}:
        return await _query_by_page(inp, db, start, end)
    elif dim_set == {"date", "query"}:
        return await _query_date_query(inp, db, start, end)
    elif dim_set == {"date", "page"}:
        return await _query_date_page(inp, db, start, end)
    elif dim_set == {"query", "page"} or dim_set == {"date", "query", "page"}:
        return await _query_query_page(inp, db, start, end)
    elif dim_set == {"searchAppearance"}:
        return await _query_appearance(inp, db, start, end)
    elif dim_set == {"searchType"}:
        return await _query_search_type(inp, db, start, end)
    else:
        # Fallback: try to handle single unsupported dimension gracefully
        return {
            "error": f"unsupported dimension combination: {dims!r}",
            "rows": [],
            "truncated": False,
            "tail_summary": None,
            "row_count": 0,
            "query_info": {
                "table": "unknown",
                "date_range": {"start": inp.date_range.start, "end": inp.date_range.end},
                "dimensions": dims,
            },
        }


async def _query_by_date(
    inp: QueryGSCInput, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    stmt = (
        select(
            GSCQueriesDaily.date,
            func.sum(GSCQueriesDaily.clicks).label("clicks"),
            func.sum(GSCQueriesDaily.impressions).label("impressions"),
            func.avg(GSCQueriesDaily.ctr).label("ctr"),
            func.avg(GSCQueriesDaily.position).label("position"),
        )
        .where(
            GSCQueriesDaily.property_id == inp.property_id,
            GSCQueriesDaily.date >= start,
            GSCQueriesDaily.date <= end,
        )
        .group_by(GSCQueriesDaily.date)
        .order_by(GSCQueriesDaily.date)
    )
    result = await db.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    for row in rows:
        if isinstance(row.get("date"), date):
            row["date"] = row["date"].isoformat()
        for k in ("ctr", "position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
    return _apply_cap_and_sort(rows, "clicks", inp.limit, inp.sort_by, "gsc_queries_daily", inp)


async def _query_by_query(
    inp: QueryGSCInput, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    stmt = (
        select(
            GSCQueriesDaily.query,
            func.sum(GSCQueriesDaily.clicks).label("clicks"),
            func.sum(GSCQueriesDaily.impressions).label("impressions"),
            func.avg(GSCQueriesDaily.ctr).label("ctr"),
            func.avg(GSCQueriesDaily.position).label("position"),
        )
        .where(
            GSCQueriesDaily.property_id == inp.property_id,
            GSCQueriesDaily.date >= start,
            GSCQueriesDaily.date <= end,
        )
        .group_by(GSCQueriesDaily.query)
    )
    result = await db.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    for row in rows:
        for k in ("ctr", "position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
    return _apply_cap_and_sort(rows, "clicks", inp.limit, inp.sort_by, "gsc_queries_daily", inp)


async def _query_by_page(
    inp: QueryGSCInput, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    stmt = (
        select(
            GSCPagesDaily.page,
            func.sum(GSCPagesDaily.clicks).label("clicks"),
            func.sum(GSCPagesDaily.impressions).label("impressions"),
            func.avg(GSCPagesDaily.ctr).label("ctr"),
            func.avg(GSCPagesDaily.position).label("position"),
        )
        .where(
            GSCPagesDaily.property_id == inp.property_id,
            GSCPagesDaily.date >= start,
            GSCPagesDaily.date <= end,
        )
        .group_by(GSCPagesDaily.page)
    )
    result = await db.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    for row in rows:
        for k in ("ctr", "position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
    return _apply_cap_and_sort(rows, "clicks", inp.limit, inp.sort_by, "gsc_pages_daily", inp)


async def _query_date_query(
    inp: QueryGSCInput, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    stmt = (
        select(
            GSCQueriesDaily.date,
            GSCQueriesDaily.query,
            func.sum(GSCQueriesDaily.clicks).label("clicks"),
            func.sum(GSCQueriesDaily.impressions).label("impressions"),
            func.avg(GSCQueriesDaily.ctr).label("ctr"),
            func.avg(GSCQueriesDaily.position).label("position"),
        )
        .where(
            GSCQueriesDaily.property_id == inp.property_id,
            GSCQueriesDaily.date >= start,
            GSCQueriesDaily.date <= end,
        )
        .group_by(GSCQueriesDaily.date, GSCQueriesDaily.query)
        .order_by(GSCQueriesDaily.date)
    )
    result = await db.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    for row in rows:
        if isinstance(row.get("date"), date):
            row["date"] = row["date"].isoformat()
        for k in ("ctr", "position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
    return _apply_cap_and_sort(rows, "clicks", inp.limit, inp.sort_by, "gsc_queries_daily", inp)


async def _query_date_page(
    inp: QueryGSCInput, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    stmt = (
        select(
            GSCPagesDaily.date,
            GSCPagesDaily.page,
            func.sum(GSCPagesDaily.clicks).label("clicks"),
            func.sum(GSCPagesDaily.impressions).label("impressions"),
            func.avg(GSCPagesDaily.ctr).label("ctr"),
            func.avg(GSCPagesDaily.position).label("position"),
        )
        .where(
            GSCPagesDaily.property_id == inp.property_id,
            GSCPagesDaily.date >= start,
            GSCPagesDaily.date <= end,
        )
        .group_by(GSCPagesDaily.date, GSCPagesDaily.page)
        .order_by(GSCPagesDaily.date)
    )
    result = await db.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    for row in rows:
        if isinstance(row.get("date"), date):
            row["date"] = row["date"].isoformat()
        for k in ("ctr", "position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
    return _apply_cap_and_sort(rows, "clicks", inp.limit, inp.sort_by, "gsc_pages_daily", inp)


async def _query_query_page(
    inp: QueryGSCInput, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    stmt = (
        select(
            GSCQueryPageDaily.query,
            GSCQueryPageDaily.page,
            func.sum(GSCQueryPageDaily.clicks).label("clicks"),
            func.sum(GSCQueryPageDaily.impressions).label("impressions"),
            func.avg(GSCQueryPageDaily.ctr).label("ctr"),
            func.avg(GSCQueryPageDaily.position).label("position"),
        )
        .where(
            GSCQueryPageDaily.property_id == inp.property_id,
            GSCQueryPageDaily.date >= start,
            GSCQueryPageDaily.date <= end,
        )
        .group_by(GSCQueryPageDaily.query, GSCQueryPageDaily.page)
    )
    result = await db.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    for row in rows:
        for k in ("ctr", "position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
    return _apply_cap_and_sort(rows, "clicks", inp.limit, inp.sort_by, "gsc_query_page_daily", inp)


async def _query_appearance(
    inp: QueryGSCInput, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    stmt = (
        select(
            GSCAppearanceDaily.search_appearance,
            func.sum(GSCAppearanceDaily.clicks).label("clicks"),
            func.sum(GSCAppearanceDaily.impressions).label("impressions"),
            func.avg(GSCAppearanceDaily.ctr).label("ctr"),
            func.avg(GSCAppearanceDaily.position).label("position"),
        )
        .where(
            GSCAppearanceDaily.property_id == inp.property_id,
            GSCAppearanceDaily.date >= start,
            GSCAppearanceDaily.date <= end,
        )
        .group_by(GSCAppearanceDaily.search_appearance)
    )
    result = await db.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    for row in rows:
        for k in ("ctr", "position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
    return _apply_cap_and_sort(rows, "clicks", inp.limit, inp.sort_by, "gsc_appearance_daily", inp)


async def _query_search_type(
    inp: QueryGSCInput, db: AsyncSession, start: date, end: date
) -> dict[str, Any]:
    stmt = (
        select(
            GSCSearchTypeDaily.search_type,
            func.sum(GSCSearchTypeDaily.clicks).label("clicks"),
            func.sum(GSCSearchTypeDaily.impressions).label("impressions"),
            func.avg(GSCSearchTypeDaily.ctr).label("ctr"),
            func.avg(GSCSearchTypeDaily.position).label("position"),
        )
        .where(
            GSCSearchTypeDaily.property_id == inp.property_id,
            GSCSearchTypeDaily.date >= start,
            GSCSearchTypeDaily.date <= end,
        )
        .group_by(GSCSearchTypeDaily.search_type)
    )
    result = await db.execute(stmt)
    rows = [dict(r) for r in result.mappings().all()]
    for row in rows:
        for k in ("ctr", "position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
    return _apply_cap_and_sort(rows, "clicks", inp.limit, inp.sort_by, "gsc_search_type_daily", inp)
