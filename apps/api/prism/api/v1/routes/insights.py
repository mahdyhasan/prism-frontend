from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.errors import NotFoundError, ValidationError
from prism.core.middleware import CurrentUser
from prism.db.models.insight import Insight
from prism.db.session import get_db_session
from prism.schemas.insights import (
    InsightGenerateResponse,
    InsightListResponse,
    InsightResponse,
    InsightStatusUpdate,
)
from prism.services.ai.insights import run_property_insights
from prism.services.properties import get_property

router = APIRouter(tags=["insights"])

_ALLOWED_USER_STATUSES = {"acknowledged", "dismissed"}
_ALLOWED_FILTER_STATUSES = {"new", "acknowledged", "dismissed"}


@router.get(
    "/properties/{property_id}/insights",
    response_model=InsightListResponse,
)
async def list_insights(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
    status: str | None = Query("new", description="new | acknowledged | dismissed"),
) -> InsightListResponse:
    await get_property(db, property_id, current_user)

    stmt = select(Insight).where(Insight.property_id == property_id)
    if status is not None:
        if status not in _ALLOWED_FILTER_STATUSES:
            raise ValidationError(f"Invalid status filter: {status}")
        stmt = stmt.where(Insight.status == status)
    stmt = stmt.order_by(Insight.detected_at.desc())

    result = await db.execute(stmt)
    items = list(result.scalars().all())

    count_stmt = select(func.count(Insight.id)).where(Insight.property_id == property_id)
    if status is not None:
        count_stmt = count_stmt.where(Insight.status == status)
    total = (await db.execute(count_stmt)).scalar_one()

    return InsightListResponse(
        items=[InsightResponse.model_validate(i) for i in items],
        total=int(total),
    )


@router.patch(
    "/properties/{property_id}/insights/{insight_id}",
    response_model=InsightResponse,
)
async def update_insight_status(
    property_id: int,
    insight_id: int,
    payload: InsightStatusUpdate,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> InsightResponse:
    await get_property(db, property_id, current_user)

    if payload.status not in _ALLOWED_USER_STATUSES:
        raise ValidationError(
            f"Invalid status: {payload.status}. Must be 'acknowledged' or 'dismissed'.",
        )

    result = await db.execute(
        select(Insight).where(
            Insight.id == insight_id,
            Insight.property_id == property_id,
        )
    )
    insight = result.scalar_one_or_none()
    if insight is None:
        raise NotFoundError("Insight not found.")

    insight.status = payload.status
    await db.commit()
    await db.refresh(insight)
    return InsightResponse.model_validate(insight)


@router.post(
    "/properties/{property_id}/insights/generate",
    response_model=InsightGenerateResponse,
)
async def trigger_insight_generation(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> InsightGenerateResponse:
    """Run every detector (anomaly + decay + cannibalization + opportunity +
    trend) for this property and persist new findings.

    Idempotent: content-hash dedupe prevents reruns from creating duplicates
    while findings haven't materially changed.
    """
    prop = await get_property(db, property_id, current_user)
    by_kind = await run_property_insights(
        db=db,
        property_id=property_id,
        tenant_id=prop.tenant_id,
    )
    return InsightGenerateResponse(
        created=sum(by_kind.values()),
        by_kind=by_kind,
    )
