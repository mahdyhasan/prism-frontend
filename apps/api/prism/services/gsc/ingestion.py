from __future__ import annotations

import asyncio
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy.dialects.mysql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.gsc import (
    GSCAppearanceDaily,
    GSCPagesDaily,
    GSCQueriesDaily,
    GSCQueryPageDaily,
    GSCSearchTypeDaily,
)
from prism.db.session import get_session_factory
from prism.services.gsc.client import get_gsc_service, run_query_with_backoff

_DEFAULT_BACKFILL_DAYS = 480   # GSC retains ~16 months
_DAILY_LOOKBACK_DAYS = 3       # GSC has ~2-3 day reporting lag
_GSC_ROW_LIMIT = 25_000        # GSC max per request


def _int(val: Any) -> int:
    try:
        return int(float(val))
    except (ValueError, TypeError):
        return 0


def _float(val: Any) -> float:
    try:
        return float(val)
    except (ValueError, TypeError):
        return 0.0


def _parse_iso_date(s: str) -> date:
    return datetime.strptime(s, "%Y-%m-%d").date()


def _query_searchanalytics(
    service: Any,
    site_url: str,
    start_date: date,
    end_date: date,
    dimensions: list[str],
    row_limit: int = _GSC_ROW_LIMIT,
    search_type: str = "web",
) -> list[dict]:
    """Execute a paginated searchanalytics.query call. Returns all rows."""
    all_rows: list[dict] = []
    start_row = 0

    while True:
        body = {
            "startDate": start_date.isoformat(),
            "endDate": end_date.isoformat(),
            "dimensions": dimensions,
            "rowLimit": row_limit,
            "startRow": start_row,
            "type": search_type,
        }
        response = run_query_with_backoff(
            lambda b=body: service.searchanalytics().query(siteUrl=site_url, body=b).execute()
        )
        rows = response.get("rows", []) or []
        if not rows:
            break

        for row in rows:
            keys = row.get("keys", [])
            record = {dim: keys[i] if i < len(keys) else "" for i, dim in enumerate(dimensions)}
            record["clicks"] = _int(row.get("clicks", 0))
            record["impressions"] = _int(row.get("impressions", 0))
            record["ctr"] = _float(row.get("ctr", 0))
            record["position"] = _float(row.get("position", 0))
            all_rows.append(record)

        if len(rows) < row_limit:
            break
        start_row += row_limit

    return all_rows


async def _upsert_queries(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": _parse_iso_date(r["date"]),
            "query": (r.get("query", "") or "")[:500],
            "country": (r.get("country", "") or "")[:100],
            "device": (r.get("device", "") or "")[:50],
            "clicks": _int(r.get("clicks", 0)),
            "impressions": _int(r.get("impressions", 0)),
            "ctr": _float(r.get("ctr", 0)),
            "position": _float(r.get("position", 0)),
        }
        for r in rows
    ]
    stmt = insert(GSCQueriesDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        clicks=stmt.inserted.clicks,
        impressions=stmt.inserted.impressions,
        ctr=stmt.inserted.ctr,
        position=stmt.inserted.position,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_pages(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": _parse_iso_date(r["date"]),
            "page": (r.get("page", "") or "")[:700],
            "clicks": _int(r.get("clicks", 0)),
            "impressions": _int(r.get("impressions", 0)),
            "ctr": _float(r.get("ctr", 0)),
            "position": _float(r.get("position", 0)),
        }
        for r in rows
    ]
    stmt = insert(GSCPagesDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        clicks=stmt.inserted.clicks,
        impressions=stmt.inserted.impressions,
        ctr=stmt.inserted.ctr,
        position=stmt.inserted.position,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_query_page(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": _parse_iso_date(r["date"]),
            "query": (r.get("query", "") or "")[:250],
            "page": (r.get("page", "") or "")[:250],
            "clicks": _int(r.get("clicks", 0)),
            "impressions": _int(r.get("impressions", 0)),
            "ctr": _float(r.get("ctr", 0)),
            "position": _float(r.get("position", 0)),
        }
        for r in rows
    ]
    stmt = insert(GSCQueryPageDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        clicks=stmt.inserted.clicks,
        impressions=stmt.inserted.impressions,
        ctr=stmt.inserted.ctr,
        position=stmt.inserted.position,
    )
    await db.execute(stmt)
    return len(records)


async def ingest_property(
    property_id: int,
    gsc_site_url: str,
    start_date: date,
    end_date: date,
    refresh_token: str | None = None,
) -> int:
    """Pull queries/pages/query+page report shapes from GSC and upsert into warehouse."""
    if not refresh_token:
        msg = "GSC ingestion requires a user refresh token."
        raise RuntimeError(msg)

    service = get_gsc_service(refresh_token)
    total_rows = 0

    loop = asyncio.get_running_loop()

    # GSC client is sync — offload each call to a thread
    def pull(dimensions: list[str]) -> list[dict]:
        return _query_searchanalytics(service, gsc_site_url, start_date, end_date, dimensions)

    queries_rows = await loop.run_in_executor(None, pull, ["date", "query", "country", "device"])
    pages_rows = await loop.run_in_executor(None, pull, ["date", "page"])
    query_page_rows = await loop.run_in_executor(None, pull, ["date", "query", "page"])

    # searchAppearance cannot be combined with ANY other dimension (GSC API restriction).
    # Query it alone and tag each row with end_date so the upsert has a date key.
    def pull_appearance() -> list[dict]:
        rows = _query_searchanalytics(
            service, gsc_site_url, start_date, end_date,
            ["searchAppearance"], search_type="web",
        )
        for r in rows:
            r["date"] = end_date.isoformat()
        return rows

    appearance_rows = await loop.run_in_executor(None, pull_appearance)

    # Per-search-type pulls — one API call each, tag rows before upsert
    search_type_rows: list[dict] = []
    for st in ("web", "image", "video", "news", "googleNews", "discover"):
        def pull_st(stype: str = st) -> list[dict]:
            try:
                return _query_searchanalytics(
                    service, gsc_site_url, start_date, end_date,
                    ["date"], search_type=stype,
                )
            except Exception as exc:
                logger.warning(
                    "GSC search-type query failed; skipping",
                    property_id=property_id,
                    search_type=stype,
                    error=str(exc),
                )
                return []

        st_rows = await loop.run_in_executor(None, pull_st)
        for r in st_rows:
            r["search_type"] = st
        search_type_rows.extend(st_rows)

    factory = get_session_factory()
    async with factory() as db:
        total_rows += await _upsert_queries(db, property_id, queries_rows)
        total_rows += await _upsert_pages(db, property_id, pages_rows)
        total_rows += await _upsert_query_page(db, property_id, query_page_rows)
        total_rows += await _upsert_appearance(db, property_id, appearance_rows)
        total_rows += await _upsert_search_type(db, property_id, search_type_rows)
        await db.commit()

    logger.info(
        "GSC ingestion complete",
        property_id=property_id,
        rows=total_rows,
        start=start_date.isoformat(),
        end=end_date.isoformat(),
    )
    return total_rows


async def run_daily_sync(
    property_id: int,
    gsc_site_url: str,
    refresh_token: str | None = None,
) -> int:
    end = date.today()
    start = end - timedelta(days=_DAILY_LOOKBACK_DAYS)
    return await ingest_property(property_id, gsc_site_url, start, end, refresh_token)


async def run_backfill(
    property_id: int,
    gsc_site_url: str,
    days: int = _DEFAULT_BACKFILL_DAYS,
    refresh_token: str | None = None,
) -> int:
    end = date.today()
    start = end - timedelta(days=days)
    return await ingest_property(property_id, gsc_site_url, start, end, refresh_token)


# ── Tier 1 dimension upserts ────────────────────────────────────────────────


async def _upsert_appearance(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": _parse_iso_date(r["date"]),
            "search_appearance": (r.get("searchAppearance", "") or "")[:100],
            "clicks": _int(r.get("clicks", 0)),
            "impressions": _int(r.get("impressions", 0)),
            "ctr": _float(r.get("ctr", 0)),
            "position": _float(r.get("position", 0)),
        }
        for r in rows
    ]
    stmt = insert(GSCAppearanceDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        clicks=stmt.inserted.clicks,
        impressions=stmt.inserted.impressions,
        ctr=stmt.inserted.ctr,
        position=stmt.inserted.position,
    )
    await db.execute(stmt)
    return len(records)


async def _upsert_search_type(db: AsyncSession, property_id: int, rows: list[dict]) -> int:
    if not rows:
        return 0
    records = [
        {
            "property_id": property_id,
            "date": _parse_iso_date(r["date"]),
            "search_type": (r.get("search_type", "") or "")[:20],
            "clicks": _int(r.get("clicks", 0)),
            "impressions": _int(r.get("impressions", 0)),
            "ctr": _float(r.get("ctr", 0)),
            "position": _float(r.get("position", 0)),
        }
        for r in rows
    ]
    stmt = insert(GSCSearchTypeDaily).values(records)
    stmt = stmt.on_duplicate_key_update(
        clicks=stmt.inserted.clicks,
        impressions=stmt.inserted.impressions,
        ctr=stmt.inserted.ctr,
        position=stmt.inserted.position,
    )
    await db.execute(stmt)
    return len(records)
