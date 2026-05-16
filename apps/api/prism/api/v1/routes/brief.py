from __future__ import annotations

import json
from datetime import date, datetime, UTC

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.middleware import CurrentUser
from prism.db.models.brief import DailyBrief
from prism.db.session import get_db_session
from prism.services.properties import get_property

router = APIRouter(tags=["brief"])

# Rate limit only applies once a brief has been successfully generated.
# Before any brief_json exists, unlimited retries are allowed so the user
# isn't locked out after a generation failure.
_MAX_REGENERATIONS_PER_DAY = 3


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------

class BriefResponse(BaseModel):
    id: int
    property_id: int
    brief_date: date
    brief_json: str | None
    generated_at: datetime
    generation_count: int

    model_config = {"from_attributes": True}


class BriefNotReadyResponse(BaseModel):
    status: str  # "not_ready" | "generating" | "error"
    brief: None = None
    message: str


class RegenerateResponse(BaseModel):
    status: str
    message: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get(
    "/properties/{property_id}/brief",
    response_model=BriefResponse | BriefNotReadyResponse,
)
async def get_daily_brief(
    property_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> BriefResponse | BriefNotReadyResponse:
    await get_property(db, property_id, current_user)

    today = date.today()
    result = await db.execute(
        select(DailyBrief).where(
            DailyBrief.property_id == property_id,
            DailyBrief.brief_date == today,
        )
    )
    brief = result.scalar_one_or_none()

    if brief is None or brief.brief_json is None:
        return BriefNotReadyResponse(
            status="not_ready",
            brief=None,
            message=(
                "Morning brief hasn't been generated yet. "
                "Trigger a manual generation or wait for the daily sync."
            ),
        )

    # Detect error marker written by generate_brief_for_property on failure.
    try:
        parsed = json.loads(brief.brief_json)
        if isinstance(parsed, dict) and "__error" in parsed:
            return BriefNotReadyResponse(
                status="error",
                brief=None,
                message=f"Generation failed: {parsed['__error']}",
            )
    except Exception:
        pass

    return BriefResponse.model_validate(brief)


@router.post(
    "/properties/{property_id}/brief/regenerate",
    response_model=RegenerateResponse,
)
async def regenerate_brief(
    property_id: int,
    background_tasks: BackgroundTasks,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> RegenerateResponse:
    await get_property(db, property_id, current_user)

    today = date.today()
    result = await db.execute(
        select(DailyBrief).where(
            DailyBrief.property_id == property_id,
            DailyBrief.brief_date == today,
        )
    )
    brief = result.scalar_one_or_none()

    # Rate limit only applies when there is already valid content.
    # If brief_json is null (generation never succeeded), always allow.
    has_content = brief is not None and brief.brief_json is not None
    if has_content and brief.generation_count >= _MAX_REGENERATIONS_PER_DAY:
        raise HTTPException(
            status_code=429,
            detail=f"Maximum {_MAX_REGENERATIONS_PER_DAY} regenerations per day reached.",
        )

    if brief is None:
        brief = DailyBrief(
            property_id=property_id,
            brief_date=today,
            brief_json=None,
            generated_at=datetime.now(UTC),
            generation_count=0,
        )
        db.add(brief)
        await db.flush()

    brief.generation_count += 1
    await db.commit()

    # Run generation in the background (no Celery required).
    # Falls back to Celery if you prefer, but BackgroundTasks works out of the box.
    from prism.ai.brief_generator import generate_brief_for_property
    background_tasks.add_task(generate_brief_for_property, property_id)

    return RegenerateResponse(
        status="queued",
        message="Brief generation started. The page will update automatically in ~30 seconds.",
    )
