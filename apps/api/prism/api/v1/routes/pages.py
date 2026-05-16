from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.middleware import CurrentUser
from prism.db.models.cross_source import XSPageDaily
from prism.db.session import get_db_session
from prism.schemas.pages import PagePerformanceResponse, PageRow
from prism.services.ga4.pages import get_page_performance
from prism.services.properties import get_property

router = APIRouter(tags=["pages"])


_ALLOWED_SORT_KEYS = {
    "sessions",
    "conv_rate",
    "engagement_rate",
    "bounce_rate",
    "avg_duration",
    "exit_rate",
    "clicks",
    "impressions",
    "position",
    "health_score",
    "frustration_score",
    "scroll_depth",
}

_ALLOWED_DEVICES = {"mobile", "desktop", "tablet"}


def _parse_dates(start: str | None, end: str | None) -> tuple[date, date]:
    today = date.today()
    if start and end:
        return date.fromisoformat(start), date.fromisoformat(end)
    return today - timedelta(days=30), today - timedelta(days=1)


@router.get(
    "/properties/{property_id}/pages",
    response_model=PagePerformanceResponse,
)
async def list_page_performance(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    min_sessions: int = Query(1, ge=0, description="Hide pages with fewer sessions than this"),
    sort_by: str = Query("sessions"),
    sort_desc: bool = Query(True),
    limit: int = Query(100, ge=1, le=500),
    device: str | None = Query(None, description="mobile | desktop | tablet (omit for all)"),
) -> PagePerformanceResponse:
    """Ranked per-page performance.

    Default path uses the GA4 + GSC materialized join (`xs_page_daily`).
    When `device` is set, switches to the GA4-only per-page-per-device table —
    GSC columns will be 0 because GSC has no device dimension at our grain.
    """
    await get_property(db, property_id, current_user)

    s, e = _parse_dates(start, end)
    sort_key = sort_by if sort_by in _ALLOWED_SORT_KEYS else "sessions"
    device_filter = device if device in _ALLOWED_DEVICES else None

    rows = await get_page_performance(
        db,
        property_id,
        s,
        e,
        min_sessions=min_sessions,
        sort_by=sort_key,  # type: ignore[arg-type]
        sort_desc=sort_desc,
        limit=limit,
        device=device_filter,
    )

    # Distinct-page count for "showing X of Y" UI
    from prism.db.models.ga4 import GA4LandingPageDeviceDaily
    if device_filter:
        total_result = await db.execute(
            select(func.count(func.distinct(GA4LandingPageDeviceDaily.landing_page)))
            .where(
                GA4LandingPageDeviceDaily.property_id == property_id,
                GA4LandingPageDeviceDaily.date >= s,
                GA4LandingPageDeviceDaily.date <= e,
                GA4LandingPageDeviceDaily.device_category == device_filter,
            )
        )
    else:
        total_result = await db.execute(
            select(func.count(func.distinct(XSPageDaily.page_url_normalized)))
            .where(
                XSPageDaily.property_id == property_id,
                XSPageDaily.date >= s,
                XSPageDaily.date <= e,
            )
        )
    total_rows = int(total_result.scalar_one() or 0)

    return PagePerformanceResponse(
        start_date=s.isoformat(),
        end_date=e.isoformat(),
        rows=[PageRow(**r) for r in rows],
        total_rows=total_rows,
        device=device_filter,
    )
