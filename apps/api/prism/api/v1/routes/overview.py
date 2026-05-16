from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Query
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import Depends

from prism.core.middleware import CurrentUser
from prism.db.session import get_db_session
from prism.schemas.overview import (
    ChannelBreakdownItem,
    HourlyHeatmapPoint,
    OverviewResponse,
    UserTypeBucket,
    UserTypeSplit,
)
from prism.services.ga4.queries import (
    get_channel_breakdown,
    get_hourly_heatmap,
    get_overview,
    get_user_type_split,
    resolve_date_range,
)

router = APIRouter(tags=["overview"])


@router.get("/properties/{property_id}/overview", response_model=OverviewResponse)
async def property_overview(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start_date: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end_date: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    preset: str | None = Query(None, description="last_7d | last_30d | last_90d | last_12m | last_14m"),
    compare_to: str | None = Query(None, description="previous_period | same_period_last_year"),
) -> OverviewResponse:
    from prism.services.properties import get_property
    # Verify user has access to this property; also pulls the property
    # so we can read its primary_conversion_events list.
    prop = await get_property(db, property_id, current_user)

    start, end = resolve_date_range(start_date, end_date, preset)
    return await get_overview(
        db, property_id, start, end, compare_to,
        primary_conversion_events=prop.primary_conversion_events or [],
    )


def _parse_dates(start: str | None, end: str | None) -> tuple[date, date]:
    today = date.today()
    if start and end:
        return date.fromisoformat(start), date.fromisoformat(end)
    return today - timedelta(days=30), today - timedelta(days=1)


@router.get(
    "/properties/{property_id}/overview/channels",
    response_model=list[ChannelBreakdownItem],
)
async def overview_channels(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end: str | None = Query(None, description="ISO date YYYY-MM-DD"),
) -> list[ChannelBreakdownItem]:
    from prism.services.properties import get_property
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    rows = await get_channel_breakdown(db, property_id, s, e)
    return [ChannelBreakdownItem(**r) for r in rows]


@router.get(
    "/properties/{property_id}/overview/hourly",
    response_model=list[HourlyHeatmapPoint],
)
async def overview_hourly(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end: str | None = Query(None, description="ISO date YYYY-MM-DD"),
) -> list[HourlyHeatmapPoint]:
    from prism.services.properties import get_property
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    rows = await get_hourly_heatmap(db, property_id, s, e)
    return [HourlyHeatmapPoint(**r) for r in rows]


@router.get(
    "/properties/{property_id}/overview/user-type",
    response_model=UserTypeSplit,
)
async def overview_user_type(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    start: str | None = Query(None, description="ISO date YYYY-MM-DD"),
    end: str | None = Query(None, description="ISO date YYYY-MM-DD"),
) -> UserTypeSplit:
    from prism.services.properties import get_property
    await get_property(db, property_id, current_user)
    s, e = _parse_dates(start, end)
    data = await get_user_type_split(db, property_id, s, e)
    return UserTypeSplit(
        new=UserTypeBucket(**data["new"]),
        returning=UserTypeBucket(**data["returning"]),
        total=UserTypeBucket(**data["total"]),
    )
