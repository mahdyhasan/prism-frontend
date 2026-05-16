from __future__ import annotations

import asyncio
from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.middleware import CurrentUser
from prism.db.models.sync import SyncJob
from prism.db.session import get_db_session
from prism.schemas.search import (
    AppearanceBreakdownItem,
    SearchDailyPoint,
    SearchKPIs,
    SearchOpportunity,
    SearchOverviewResponse,
    SearchPage,
    SearchQuery,
    SearchTypeBreakdownItem,
)
from prism.services.gsc.queries import (
    get_appearance_breakdown,
    get_daily_trend,
    get_opportunities,
    get_search_kpis,
    get_search_type_breakdown,
    get_top_pages,
    get_top_queries,
)
from prism.services.properties import get_property

router = APIRouter(tags=["search"])


def _parse_dates(start: str | None, end: str | None) -> tuple[date, date]:
    today = date.today()
    if start and end:
        return date.fromisoformat(start), date.fromisoformat(end)
    return today - timedelta(days=30), today - timedelta(days=1)


def _previous_period(start: date, end: date) -> tuple[date, date]:
    delta = (end - start).days + 1
    cend = start - timedelta(days=1)
    cstart = cend - timedelta(days=delta - 1)
    return cstart, cend


@router.get(
    "/properties/{property_id}/search/overview",
    response_model=SearchOverviewResponse,
)
async def search_overview(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    compare: bool = Query(True, description="Include previous-period comparison"),
) -> SearchOverviewResponse:
    await get_property(db, property_id, current_user)

    s, e = _parse_dates(start, end)
    cs: date | None
    ce: date | None
    if compare:
        cs, ce = _previous_period(s, e)
    else:
        cs, ce = None, None

    kpis_raw, trend_raw, top_q, top_p, opps = await asyncio.gather(
        get_search_kpis(db, property_id, s, e, cs, ce),
        get_daily_trend(db, property_id, s, e),
        get_top_queries(db, property_id, s, e, limit=50),
        get_top_pages(db, property_id, s, e, limit=50),
        get_opportunities(db, property_id, s, e, limit=20),
    )

    kpis = SearchKPIs(**kpis_raw)

    sync_result = await db.execute(
        select(SyncJob.finished_at)
        .where(
            SyncJob.property_id == property_id,
            SyncJob.source == "gsc",
            SyncJob.status == "done",
        )
        .order_by(SyncJob.finished_at.desc())
        .limit(1)
    )
    last_sync = sync_result.scalar_one_or_none()

    return SearchOverviewResponse(
        start_date=s.isoformat(),
        end_date=e.isoformat(),
        compare_start_date=cs.isoformat() if cs else None,
        compare_end_date=ce.isoformat() if ce else None,
        kpis=kpis,
        daily_trend=[SearchDailyPoint(**r) for r in trend_raw],
        top_queries=[SearchQuery(**r) for r in top_q],
        top_pages=[SearchPage(**r) for r in top_p],
        opportunities=[SearchOpportunity(**r) for r in opps],
        last_synced_at=last_sync.isoformat() if last_sync else None,
    )


@router.get(
    "/properties/{property_id}/search/queries",
    response_model=list[SearchQuery],
)
async def search_queries(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> list[SearchQuery]:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    rows = await get_top_queries(db, property_id, s, e, limit=limit)
    return [SearchQuery(**r) for r in rows]


@router.get(
    "/properties/{property_id}/search/pages",
    response_model=list[SearchPage],
)
async def search_pages(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
) -> list[SearchPage]:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    rows = await get_top_pages(db, property_id, s, e, limit=limit)
    return [SearchPage(**r) for r in rows]


@router.get(
    "/properties/{property_id}/search/opportunities",
    response_model=list[SearchOpportunity],
)
async def search_opportunities(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
) -> list[SearchOpportunity]:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    rows = await get_opportunities(db, property_id, s, e, limit=limit)
    return [SearchOpportunity(**r) for r in rows]


@router.get(
    "/properties/{property_id}/search/appearance",
    response_model=list[AppearanceBreakdownItem],
)
async def search_appearance(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end: str | None = Query(None, description="ISO date YYYY-MM-DD"),
) -> list[AppearanceBreakdownItem]:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    rows = await get_appearance_breakdown(db, property_id, s, e)
    return [AppearanceBreakdownItem(**r) for r in rows]


@router.get(
    "/properties/{property_id}/search/types",
    response_model=list[SearchTypeBreakdownItem],
)
async def search_types(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end: str | None = Query(None, description="ISO date YYYY-MM-DD"),
) -> list[SearchTypeBreakdownItem]:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    rows = await get_search_type_breakdown(db, property_id, s, e)
    return [SearchTypeBreakdownItem(**r) for r in rows]
