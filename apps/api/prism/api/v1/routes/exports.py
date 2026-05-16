"""CSV export endpoints — one per warehouse table.

Every endpoint:
  1. authenticates via CurrentUser
  2. verifies property membership via get_property
  3. parses the start/end query params (defaults: last 30 days)
  4. streams the CSV body with a Content-Disposition attachment header
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.middleware import CurrentUser
from prism.db.session import get_db_session
from prism.services.exports import (
    export_ga4_daily_metrics_csv,
    export_ga4_devices_csv,
    export_ga4_geo_csv,
    export_ga4_landing_pages_csv,
    export_ga4_traffic_sources_csv,
    export_gsc_pages_csv,
    export_gsc_queries_csv,
)
from prism.services.properties import get_property

router = APIRouter(
    prefix="/properties/{property_id}/exports",
    tags=["exports"],
)


def _parse_dates(start: str | None, end: str | None) -> tuple[date, date]:
    today = date.today()
    if start and end:
        return date.fromisoformat(start), date.fromisoformat(end)
    return today - timedelta(days=30), today - timedelta(days=1)


def _csv_response(body: str, kind: str, start: date, end: date) -> Response:
    filename = f"prism_{kind}_{start.isoformat()}_{end.isoformat()}.csv"
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ga4/sessions.csv")
async def export_ga4_sessions(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end: str | None = Query(None, description="ISO date YYYY-MM-DD"),
) -> Response:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    body = await export_ga4_daily_metrics_csv(db, property_id, s, e)
    return _csv_response(body, "sessions", s, e)


@router.get("/ga4/pages.csv")
async def export_ga4_pages(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> Response:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    body = await export_ga4_landing_pages_csv(db, property_id, s, e)
    return _csv_response(body, "pages", s, e)


@router.get("/ga4/sources.csv")
async def export_ga4_sources(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> Response:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    body = await export_ga4_traffic_sources_csv(db, property_id, s, e)
    return _csv_response(body, "sources", s, e)


@router.get("/ga4/devices.csv")
async def export_ga4_devices(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> Response:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    body = await export_ga4_devices_csv(db, property_id, s, e)
    return _csv_response(body, "devices", s, e)


@router.get("/ga4/geo.csv")
async def export_ga4_geo(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> Response:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    body = await export_ga4_geo_csv(db, property_id, s, e)
    return _csv_response(body, "geo", s, e)


@router.get("/gsc/queries.csv")
async def export_gsc_queries(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> Response:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    body = await export_gsc_queries_csv(db, property_id, s, e)
    return _csv_response(body, "queries", s, e)


@router.get("/gsc/pages.csv")
async def export_gsc_pages(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None),
    end: str | None = Query(None),
) -> Response:
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    body = await export_gsc_pages_csv(db, property_id, s, e)
    return _csv_response(body, "gsc_pages", s, e)
