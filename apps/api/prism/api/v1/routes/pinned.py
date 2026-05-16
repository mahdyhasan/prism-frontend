from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.errors import NotFoundError
from prism.core.middleware import CurrentUser
from prism.db.models.chat import PinnedQuestion, PinnedQuestionRun
from prism.db.session import get_db_session
from prism.services.properties import get_property

router = APIRouter(prefix="/pinned", tags=["pinned"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CreatePinnedRequest(BaseModel):
    property_id: int
    title: str
    prompt: str
    source_scope: str = "all"
    date_range_strategy: str = "rolling_28d"
    tags: list[str] = []


class PinnedRunResponse(BaseModel):
    id: int
    pin_id: int
    run_at: datetime
    answer_json: str | None
    run_status: str
    error: str | None

    model_config = {"from_attributes": True}


class PinnedResponse(BaseModel):
    id: int
    property_id: int
    user_id: int
    title: str
    prompt: str
    source_scope: str
    date_range_strategy: str
    tags: list | None
    latest_run: PinnedRunResponse | None = None

    model_config = {"from_attributes": True}


class TriggerRunResponse(BaseModel):
    status: str
    run_id: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _assert_pin_access(db: AsyncSession, pin_id: int, user_id: int) -> PinnedQuestion:
    result = await db.execute(
        select(PinnedQuestion).where(PinnedQuestion.id == pin_id)
    )
    pin = result.scalar_one_or_none()
    if pin is None:
        raise NotFoundError("Pinned question not found.")
    if pin.user_id != user_id:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Access denied to this pinned question.")
    return pin


async def _latest_run(db: AsyncSession, pin_id: int) -> PinnedQuestionRun | None:
    result = await db.execute(
        select(PinnedQuestionRun)
        .where(PinnedQuestionRun.pin_id == pin_id)
        .order_by(PinnedQuestionRun.run_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none()


def _pin_to_response(pin: PinnedQuestion, run: PinnedQuestionRun | None) -> PinnedResponse:
    return PinnedResponse(
        id=pin.id,
        property_id=pin.property_id,
        user_id=pin.user_id,
        title=pin.title,
        prompt=pin.prompt,
        source_scope=pin.source_scope,
        date_range_strategy=pin.date_range_strategy,
        tags=pin.tags,
        latest_run=PinnedRunResponse.model_validate(run) if run is not None else None,
    )


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[PinnedResponse])
async def list_pinned(
    current_user: CurrentUser,
    property_id: int = Query(..., description="Property to filter by"),
    db: AsyncSession = Depends(get_db_session),
) -> list[PinnedResponse]:
    await get_property(db, property_id, current_user)

    result = await db.execute(
        select(PinnedQuestion).where(
            PinnedQuestion.property_id == property_id,
            PinnedQuestion.user_id == current_user.id,
        )
    )
    pins = result.scalars().all()

    out = []
    for pin in pins:
        run = await _latest_run(db, pin.id)
        out.append(_pin_to_response(pin, run))
    return out


@router.post("", response_model=PinnedResponse, status_code=201)
async def create_pinned(
    body: CreatePinnedRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PinnedResponse:
    await get_property(db, body.property_id, current_user)

    pin = PinnedQuestion(
        property_id=body.property_id,
        user_id=current_user.id,
        title=body.title,
        prompt=body.prompt,
        source_scope=body.source_scope,
        date_range_strategy=body.date_range_strategy,
        tags=body.tags or [],
    )
    db.add(pin)
    await db.commit()
    await db.refresh(pin)
    return _pin_to_response(pin, None)


@router.get("/{pin_id}", response_model=PinnedResponse)
async def get_pinned(
    pin_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> PinnedResponse:
    pin = await _assert_pin_access(db, pin_id, current_user.id)
    run = await _latest_run(db, pin.id)
    return _pin_to_response(pin, run)


@router.delete("/{pin_id}")
async def delete_pinned(
    pin_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> dict:
    pin = await _assert_pin_access(db, pin_id, current_user.id)
    await db.delete(pin)
    await db.commit()
    return {"success": True}


@router.post("/{pin_id}/run", response_model=TriggerRunResponse)
async def trigger_run(
    pin_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> TriggerRunResponse:
    pin = await _assert_pin_access(db, pin_id, current_user.id)

    run = PinnedQuestionRun(
        pin_id=pin.id,
        run_status="pending",
        answer_json=None,
        error=None,
    )
    db.add(run)
    await db.commit()
    await db.refresh(run)

    from prism.workers.tasks import run_pinned_question
    run_pinned_question.delay(pin_id=pin.id, run_id=run.id)

    return TriggerRunResponse(status="queued", run_id=run.id)


@router.get("/{pin_id}/runs", response_model=list[PinnedRunResponse])
async def list_runs(
    pin_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> list[PinnedRunResponse]:
    await _assert_pin_access(db, pin_id, current_user.id)

    result = await db.execute(
        select(PinnedQuestionRun)
        .where(PinnedQuestionRun.pin_id == pin_id)
        .order_by(PinnedQuestionRun.run_at.desc())
    )
    runs = result.scalars().all()
    return [PinnedRunResponse.model_validate(r) for r in runs]
