from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.cross_source import XSPageDaily
from prism.db.models.gsc import GSCQueriesDaily, GSCQueryPageDaily
from prism.ai.tools.schemas import (
    CannibalizationInput,
    ContentDecayInput,
    CorrelatePageInput,
    IntentVsOutcomeInput,
    SerpOpportunityInput,
    VanityVsValueInput,
)


def _parse_date(d: str) -> date:
    return date.fromisoformat(d)


# ---------------------------------------------------------------------------
# correlate_page_performance
# ---------------------------------------------------------------------------

async def correlate_page_performance(inp: CorrelatePageInput, db: AsyncSession) -> dict[str, Any]:
    start = _parse_date(inp.date_range.start)
    end = _parse_date(inp.date_range.end)

    pattern = inp.page_pattern
    use_prefix = pattern.endswith("/")

    stmt = (
        select(
            XSPageDaily.page_url_normalized,
            func.sum(XSPageDaily.sessions).label("sessions"),
            func.sum(XSPageDaily.users).label("users"),
            func.sum(XSPageDaily.conversions).label("conversions"),
            func.sum(XSPageDaily.revenue).label("revenue"),
            func.avg(XSPageDaily.bounce_rate).label("bounce_rate"),
            func.avg(XSPageDaily.avg_session_duration).label("avg_session_duration"),
            func.sum(XSPageDaily.clicks).label("clicks"),
            func.sum(XSPageDaily.impressions).label("impressions"),
            func.avg(XSPageDaily.ctr).label("ctr"),
            func.avg(XSPageDaily.avg_position).label("avg_position"),
        )
        .where(
            XSPageDaily.property_id == inp.property_id,
            XSPageDaily.date >= start,
            XSPageDaily.date <= end,
        )
        .group_by(XSPageDaily.page_url_normalized)
    )

    if use_prefix:
        stmt = stmt.where(XSPageDaily.page_url_normalized.like(f"{pattern}%"))
    else:
        stmt = stmt.where(XSPageDaily.page_url_normalized == pattern)

    result = await db.execute(stmt)
    rows_raw = result.mappings().all()

    pages: list[dict[str, Any]] = []
    for r in rows_raw:
        row = dict(r)
        for k in ("bounce_rate", "avg_session_duration", "ctr", "avg_position"):
            if row.get(k) is not None:
                row[k] = round(float(row[k]), 4)
        # Join confidence per page
        has_ga4 = (row.get("sessions") or 0) > 0
        has_gsc = (row.get("impressions") or 0) > 0
        row["join_confidence"] = "high" if (has_ga4 and has_gsc) else "medium"
        pages.append(row)

    overall_confidence = "high" if all(p["join_confidence"] == "high" for p in pages) and pages else "medium"

    return {
        "pages": pages,
        "join_confidence": overall_confidence,
        "row_count": len(pages),
    }


# ---------------------------------------------------------------------------
# intent_vs_outcome
# ---------------------------------------------------------------------------

async def intent_vs_outcome(inp: IntentVsOutcomeInput, db: AsyncSession) -> dict[str, Any]:
    start = _parse_date(inp.date_range.start)
    end = _parse_date(inp.date_range.end)

    # Split date range into two halves
    total_days = (end - start).days + 1
    half_days = total_days // 2
    mid = start + timedelta(days=half_days - 1)
    second_start = mid + timedelta(days=1)

    async def _aggregate_half(h_start: date, h_end: date) -> dict[str, dict[str, Any]]:
        stmt = (
            select(
                XSPageDaily.page_url_normalized,
                func.sum(XSPageDaily.impressions).label("impressions"),
                func.sum(XSPageDaily.conversions).label("conversions"),
                func.sum(XSPageDaily.sessions).label("sessions"),
            )
            .where(
                XSPageDaily.property_id == inp.property_id,
                XSPageDaily.date >= h_start,
                XSPageDaily.date <= h_end,
            )
            .group_by(XSPageDaily.page_url_normalized)
        )
        result = await db.execute(stmt)
        return {r.page_url_normalized: dict(r._mapping) for r in result}

    first_half = await _aggregate_half(start, mid)
    second_half = await _aggregate_half(second_start, end)

    all_pages = set(first_half) | set(second_half)

    intent_exceeded: list[dict[str, Any]] = []
    outcome_exceeded: list[dict[str, Any]] = []

    for page in all_pages:
        a = first_half.get(page, {"impressions": 0, "conversions": 0, "sessions": 0})
        b = second_half.get(page, {"impressions": 0, "conversions": 0, "sessions": 0})

        imp_a = float(a.get("impressions") or 0)
        imp_b = float(b.get("impressions") or 0)
        conv_a = float(a.get("conversions") or 0)
        conv_b = float(b.get("conversions") or 0)

        if imp_a == 0:
            continue

        imp_delta_pct = (imp_b - imp_a) / imp_a * 100
        conv_delta_pct = (conv_b - conv_a) / conv_a * 100 if conv_a > 0 else (100.0 if conv_b > 0 else 0.0)

        entry = {
            "page": page,
            "impressions_first": imp_a,
            "impressions_second": imp_b,
            "impressions_delta_pct": round(imp_delta_pct, 2),
            "conversions_first": conv_a,
            "conversions_second": conv_b,
            "conversions_delta_pct": round(conv_delta_pct, 2),
        }

        if imp_delta_pct >= inp.min_impression_delta_pct and conv_delta_pct < (imp_delta_pct * 0.5):
            intent_exceeded.append(entry)
        elif conv_delta_pct >= inp.min_impression_delta_pct and imp_delta_pct < (conv_delta_pct * 0.5):
            outcome_exceeded.append(entry)

    intent_exceeded.sort(key=lambda x: x["impressions_delta_pct"], reverse=True)
    outcome_exceeded.sort(key=lambda x: x["conversions_delta_pct"], reverse=True)

    return {
        "intent_exceeded_outcome": intent_exceeded,
        "outcome_exceeded_intent": outcome_exceeded,
    }


# ---------------------------------------------------------------------------
# vanity_vs_value_queries
# ---------------------------------------------------------------------------

async def vanity_vs_value_queries(inp: VanityVsValueInput, db: AsyncSession) -> dict[str, Any]:
    start = _parse_date(inp.date_range.start)
    end = _parse_date(inp.date_range.end)

    # Get query -> page data from gsc_query_page_daily
    qp_stmt = (
        select(
            GSCQueryPageDaily.query,
            GSCQueryPageDaily.page,
            func.sum(GSCQueryPageDaily.clicks).label("clicks"),
            func.sum(GSCQueryPageDaily.impressions).label("impressions"),
        )
        .where(
            GSCQueryPageDaily.property_id == inp.property_id,
            GSCQueryPageDaily.date >= start,
            GSCQueryPageDaily.date <= end,
        )
        .group_by(GSCQueryPageDaily.query, GSCQueryPageDaily.page)
    )
    qp_result = await db.execute(qp_stmt)
    qp_rows = qp_result.mappings().all()

    if not qp_rows:
        return {"items": [], "row_count": 0}

    # Get conversion rates from xs_page_daily per page
    pages_in_scope = {r.page for r in qp_rows}
    xs_stmt = (
        select(
            XSPageDaily.page_url_normalized,
            func.sum(XSPageDaily.conversions).label("conversions"),
            func.sum(XSPageDaily.sessions).label("sessions"),
        )
        .where(
            XSPageDaily.property_id == inp.property_id,
            XSPageDaily.date >= start,
            XSPageDaily.date <= end,
            XSPageDaily.page_url_normalized.in_(pages_in_scope),
        )
        .group_by(XSPageDaily.page_url_normalized)
    )
    xs_result = await db.execute(xs_stmt)
    conversion_rate_map: dict[str, float] = {}
    for r in xs_result.mappings().all():
        sessions = float(r.sessions or 0)
        conversions = float(r.conversions or 0)
        conversion_rate_map[r.page_url_normalized] = conversions / sessions if sessions > 0 else 0.0

    # Aggregate by query (sum clicks across pages, use max conversion rate page for value score)
    query_map: dict[str, dict[str, Any]] = {}
    for r in qp_rows:
        q = r.query
        clicks = int(r.clicks or 0)
        page = r.page
        cr = conversion_rate_map.get(page, 0.0)
        value = clicks * cr

        if q not in query_map:
            query_map[q] = {
                "query": q,
                "total_clicks": 0,
                "total_impressions": 0,
                "best_page": page,
                "best_page_conversion_rate": cr,
                "value_score": 0.0,
            }

        query_map[q]["total_clicks"] += clicks
        query_map[q]["total_impressions"] += int(r.impressions or 0)
        if cr > query_map[q]["best_page_conversion_rate"]:
            query_map[q]["best_page"] = page
            query_map[q]["best_page_conversion_rate"] = cr

        query_map[q]["value_score"] += value

    items = list(query_map.values())
    for item in items:
        item["value_score"] = round(item["value_score"], 4)
        item["best_page_conversion_rate"] = round(item["best_page_conversion_rate"], 4)

    # Sort by value_score desc
    items.sort(key=lambda x: x["value_score"], reverse=True)
    items = items[: inp.limit]

    return {"items": items, "row_count": len(items)}


# ---------------------------------------------------------------------------
# cannibalization_scan
# ---------------------------------------------------------------------------

async def cannibalization_scan(inp: CannibalizationInput, db: AsyncSession) -> dict[str, Any]:
    start = _parse_date(inp.date_range.start)
    end = _parse_date(inp.date_range.end)

    total_days = max((end - start).days + 1, 1)

    # Find query+page pairs that meet impression threshold
    stmt = (
        select(
            GSCQueryPageDaily.query,
            GSCQueryPageDaily.page,
            func.sum(GSCQueryPageDaily.impressions).label("total_impressions"),
            func.sum(GSCQueryPageDaily.clicks).label("total_clicks"),
            func.avg(GSCQueryPageDaily.position).label("avg_position"),
        )
        .where(
            GSCQueryPageDaily.property_id == inp.property_id,
            GSCQueryPageDaily.date >= start,
            GSCQueryPageDaily.date <= end,
        )
        .group_by(GSCQueryPageDaily.query, GSCQueryPageDaily.page)
        .having(func.sum(GSCQueryPageDaily.impressions) >= inp.impression_threshold * total_days)
    )
    result = await db.execute(stmt)
    rows = result.mappings().all()

    # Group by query, find queries with 2+ competing pages
    query_pages: dict[str, list[dict[str, Any]]] = {}
    for r in rows:
        q = r.query
        if q not in query_pages:
            query_pages[q] = []
        query_pages[q].append({
            "page": r.page,
            "total_impressions": int(r.total_impressions or 0),
            "total_clicks": int(r.total_clicks or 0),
            "avg_position": round(float(r.avg_position or 0), 2),
        })

    cannibalized_queries = {q: pages for q, pages in query_pages.items() if len(pages) >= 2}

    if not cannibalized_queries:
        return {"cannibalized_queries": []}

    # Cross-reference xs_page_daily to find which page converts better
    all_pages = {p["page"] for pages in cannibalized_queries.values() for p in pages}
    xs_stmt = (
        select(
            XSPageDaily.page_url_normalized,
            func.sum(XSPageDaily.conversions).label("conversions"),
            func.sum(XSPageDaily.sessions).label("sessions"),
        )
        .where(
            XSPageDaily.property_id == inp.property_id,
            XSPageDaily.date >= start,
            XSPageDaily.date <= end,
            XSPageDaily.page_url_normalized.in_(all_pages),
        )
        .group_by(XSPageDaily.page_url_normalized)
    )
    xs_result = await db.execute(xs_stmt)
    conversion_map: dict[str, float] = {}
    for r in xs_result.mappings().all():
        sessions = float(r.sessions or 0)
        conversions = float(r.conversions or 0)
        conversion_map[r.page_url_normalized] = conversions / sessions if sessions > 0 else 0.0

    output: list[dict[str, Any]] = []
    for query, pages in cannibalized_queries.items():
        for p in pages:
            p["conversion_rate"] = round(conversion_map.get(p["page"], 0.0), 4)

        # Recommend page with highest conversion rate; if tied, use best avg_position
        pages_sorted = sorted(
            pages,
            key=lambda x: (x["conversion_rate"], -x["avg_position"]),
            reverse=True,
        )
        canonical = pages_sorted[0]["page"] if pages_sorted else None

        output.append({
            "query": query,
            "competing_pages": pages_sorted,
            "recommended_canonical": canonical,
        })

    output.sort(key=lambda x: sum(p["total_impressions"] for p in x["competing_pages"]), reverse=True)

    return {"cannibalized_queries": output}


# ---------------------------------------------------------------------------
# serp_opportunity_scan
# ---------------------------------------------------------------------------

async def serp_opportunity_scan(inp: SerpOpportunityInput, db: AsyncSession) -> dict[str, Any]:
    # Use a broad date range: last 28 days implied by the input (no date range on this tool)
    # We look at gsc_queries_daily for recent data; use all available data for the property
    # and rely on avg_position filtering.
    stmt = (
        select(
            GSCQueriesDaily.query,
            func.avg(GSCQueriesDaily.position).label("avg_position"),
            func.sum(GSCQueriesDaily.impressions).label("total_impressions"),
            func.sum(GSCQueriesDaily.clicks).label("total_clicks"),
            func.avg(GSCQueriesDaily.ctr).label("avg_ctr"),
            func.count(GSCQueriesDaily.date.distinct()).label("days_with_data"),
        )
        .where(GSCQueriesDaily.property_id == inp.property_id)
        .group_by(GSCQueriesDaily.query)
        .having(
            func.avg(GSCQueriesDaily.position) >= inp.min_position,
            func.avg(GSCQueriesDaily.position) <= inp.max_position,
        )
    )
    result = await db.execute(stmt)
    rows = result.mappings().all()

    opportunities: list[dict[str, Any]] = []
    for r in rows:
        days = int(r.days_with_data or 1)
        total_impressions = int(r.total_impressions or 0)
        avg_daily_impressions = total_impressions / days if days > 0 else 0

        if avg_daily_impressions < inp.min_impressions:
            continue

        opportunities.append({
            "query": r.query,
            "avg_position": round(float(r.avg_position or 0), 2),
            "total_impressions": total_impressions,
            "avg_daily_impressions": round(avg_daily_impressions, 2),
            "total_clicks": int(r.total_clicks or 0),
            "avg_ctr": round(float(r.avg_ctr or 0), 4),
            "ga4_page": None,
            "ga4_sessions": None,
            "ga4_conversions": None,
        })

    if not opportunities:
        return {"opportunities": []}

    # Try to join with xs_page_daily via gsc_query_page_daily for GA4 context
    queries_in_scope = [o["query"] for o in opportunities]
    qp_stmt = (
        select(
            GSCQueryPageDaily.query,
            GSCQueryPageDaily.page,
            func.sum(GSCQueryPageDaily.impressions).label("total_impressions"),
        )
        .where(
            GSCQueryPageDaily.property_id == inp.property_id,
            GSCQueryPageDaily.query.in_(queries_in_scope),
        )
        .group_by(GSCQueryPageDaily.query, GSCQueryPageDaily.page)
    )
    qp_result = await db.execute(qp_stmt)
    # Best page per query (most impressions)
    query_best_page: dict[str, str] = {}
    query_page_imp: dict[str, int] = {}
    for r in qp_result.mappings().all():
        q = r.query
        imp = int(r.total_impressions or 0)
        if imp > query_page_imp.get(q, -1):
            query_best_page[q] = r.page
            query_page_imp[q] = imp

    all_pages = set(query_best_page.values())
    if all_pages:
        xs_stmt = (
            select(
                XSPageDaily.page_url_normalized,
                func.sum(XSPageDaily.sessions).label("sessions"),
                func.sum(XSPageDaily.conversions).label("conversions"),
            )
            .where(
                XSPageDaily.property_id == inp.property_id,
                XSPageDaily.page_url_normalized.in_(all_pages),
            )
            .group_by(XSPageDaily.page_url_normalized)
        )
        xs_result = await db.execute(xs_stmt)
        page_ga4: dict[str, dict[str, Any]] = {
            r.page_url_normalized: {
                "sessions": int(r.sessions or 0),
                "conversions": int(r.conversions or 0),
            }
            for r in xs_result.mappings().all()
        }

        for opp in opportunities:
            best_page = query_best_page.get(opp["query"])
            if best_page and best_page in page_ga4:
                opp["ga4_page"] = best_page
                opp["ga4_sessions"] = page_ga4[best_page]["sessions"]
                opp["ga4_conversions"] = page_ga4[best_page]["conversions"]

    opportunities.sort(key=lambda x: x["total_impressions"], reverse=True)

    return {"opportunities": opportunities}


# ---------------------------------------------------------------------------
# content_decay_scan
# ---------------------------------------------------------------------------

async def content_decay_scan(inp: ContentDecayInput, db: AsyncSession) -> dict[str, Any]:
    end = date.today()
    start = end - timedelta(days=inp.lookback_days - 1)

    half_days = inp.lookback_days // 2
    mid = start + timedelta(days=half_days - 1)
    second_start = mid + timedelta(days=1)

    async def _half_aggregate(h_start: date, h_end: date) -> dict[str, dict[str, Any]]:
        stmt = (
            select(
                XSPageDaily.page_url_normalized,
                func.sum(XSPageDaily.sessions).label("sessions"),
                func.sum(XSPageDaily.impressions).label("impressions"),
                func.avg(XSPageDaily.avg_position).label("avg_position"),
                func.avg(XSPageDaily.ctr).label("ctr"),
                func.sum(XSPageDaily.clicks).label("clicks"),
            )
            .where(
                XSPageDaily.property_id == inp.property_id,
                XSPageDaily.date >= h_start,
                XSPageDaily.date <= h_end,
            )
            .group_by(XSPageDaily.page_url_normalized)
        )
        result = await db.execute(stmt)
        return {r.page_url_normalized: dict(r._mapping) for r in result}

    first_half = await _half_aggregate(start, mid)
    second_half = await _half_aggregate(second_start, end)

    decaying: list[dict[str, Any]] = []

    for page, a in first_half.items():
        sessions_a = float(a.get("sessions") or 0)
        if sessions_a < inp.min_sessions_threshold:
            continue

        b = second_half.get(page, {})
        sessions_b = float(b.get("sessions") or 0)

        if sessions_a == 0:
            continue

        session_delta_pct = (sessions_b - sessions_a) / sessions_a * 100
        if session_delta_pct >= -20.0:
            # Not decaying
            continue

        imp_a = float(a.get("impressions") or 0)
        imp_b = float(b.get("impressions") or 0)
        pos_a = float(a.get("avg_position") or 0)
        pos_b = float(b.get("avg_position") or 0)
        ctr_a = float(a.get("ctr") or 0)
        ctr_b = float(b.get("ctr") or 0)

        has_gsc = imp_a > 0

        # Classify decay type
        if not has_gsc:
            decay_type = "ga4_only"
        elif pos_b > pos_a * 1.1 and pos_a > 0:
            decay_type = "ranking_loss"
        elif imp_b >= imp_a * 0.9 and ctr_b < ctr_a * 0.9 and ctr_a > 0:
            decay_type = "ctr_loss"
        elif imp_b < imp_a * 0.8 and imp_a > 0:
            decay_type = "demand_loss"
        else:
            decay_type = "ga4_only"

        decaying.append({
            "page": page,
            "decay_type": decay_type,
            "sessions_first_half": round(sessions_a, 0),
            "sessions_second_half": round(sessions_b, 0),
            "session_delta_pct": round(session_delta_pct, 2),
            "impressions_first_half": round(imp_a, 0),
            "impressions_second_half": round(imp_b, 0),
            "avg_position_first_half": round(pos_a, 2) if pos_a else None,
            "avg_position_second_half": round(pos_b, 2) if pos_b else None,
            "ctr_first_half": round(ctr_a, 4) if ctr_a else None,
            "ctr_second_half": round(ctr_b, 4) if ctr_b else None,
        })

    decaying.sort(key=lambda x: x["session_delta_pct"])

    return {"decaying_pages": decaying}
