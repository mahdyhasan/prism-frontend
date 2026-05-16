"""Actions API routes.

Exposes the action lifecycle (confirm / cancel / list) to the frontend.
The chat agent creates pending actions; these endpoints let the UI surface them
for user approval and mark them confirmed or cancelled.

Endpoints:
  GET  /actions?property_id=&status=  — list actions (recent or pending)
  GET  /actions/{action_id}           — fetch one action
  POST /actions/{action_id}/confirm   — confirm + execute
  POST /actions/{action_id}/cancel    — cancel
"""
from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.errors import NotFoundError
from prism.core.middleware import CurrentUser
from prism.db.models.actions import ActionExecution
from prism.db.models.property import Property, PropertyMember
from prism.db.session import get_db_session

router = APIRouter(prefix="/actions", tags=["actions"])


# ---------------------------------------------------------------------------
# Response schema
# ---------------------------------------------------------------------------

class ActionResponse(BaseModel):
    id: int
    property_id: int
    tool_name: str
    tool_input: dict[str, Any]
    status: str
    confirmation_required: bool
    created_at: datetime
    confirmed_at: datetime | None
    executed_at: datetime | None
    result: dict[str, Any] | None
    error: str | None
    # Included only when status == "pending_confirmation"; the frontend
    # must echo this back in POST /actions/{id}/confirm.
    confirmation_token: str | None = None

    model_config = {"from_attributes": True}


class ConfirmRequest(BaseModel):
    token: str


# ---------------------------------------------------------------------------
# Response builder (injects HMAC token for pending actions)
# ---------------------------------------------------------------------------

def _build_response(action: ActionExecution) -> ActionResponse:
    from prism.config import get_settings
    from prism.services.actions.confirmation import generate_confirmation_token

    r = ActionResponse.model_validate(action)
    if action.status == "pending_confirmation":
        settings = get_settings()
        r.confirmation_token = generate_confirmation_token(action.id, settings.actions_hmac_secret)
    return r


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _assert_property_access(
    db: AsyncSession,
    property_id: int,
    user_id: int,
) -> Property:
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop = result.scalar_one_or_none()
    if prop is None:
        raise NotFoundError("Property not found.")
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user_id,
        )
    )
    member = member_result.scalar_one_or_none()
    is_creator = prop.linked_by_user_id == user_id
    if member is None and not is_creator:
        raise HTTPException(status_code=403, detail="Access denied.")
    return prop


async def _get_action_for_user(
    db: AsyncSession,
    action_id: int,
    user_id: int,
) -> ActionExecution:
    result = await db.execute(
        select(ActionExecution).where(ActionExecution.id == action_id)
    )
    action = result.scalar_one_or_none()
    if action is None:
        raise NotFoundError("Action not found.")
    # Ownership check: must be the user who triggered it OR have property access
    if action.user_id != user_id:
        await _assert_property_access(db, action.property_id, user_id)
    return action


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.get("", response_model=list[ActionResponse])
async def list_actions(
    current_user: CurrentUser,
    property_id: int = Query(..., description="Filter by property"),
    status: str | None = Query(None, description="Filter by status (e.g. pending_confirmation)"),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
) -> list[ActionResponse]:
    await _assert_property_access(db, property_id, current_user.id)

    stmt = (
        select(ActionExecution)
        .where(ActionExecution.property_id == property_id)
        .order_by(ActionExecution.created_at.desc())
        .limit(limit)
    )
    if status:
        stmt = stmt.where(ActionExecution.status == status)

    result = await db.execute(stmt)
    actions = result.scalars().all()
    return [_build_response(a) for a in actions]


@router.get("/{action_id}", response_model=ActionResponse)
async def get_action(
    action_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> ActionResponse:
    action = await _get_action_for_user(db, action_id, current_user.id)
    return _build_response(action)


@router.post("/{action_id}/confirm", response_model=ActionResponse)
async def confirm_action(
    action_id: int,
    body: ConfirmRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> ActionResponse:
    """Confirm a pending action.

    The caller must echo back the ``confirmation_token`` returned in the
    GET /actions/{id} response.  Status must be 'pending_confirmation' and
    the action must not have exceeded the 10-minute TTL.
    """
    from prism.config import get_settings
    from prism.services.actions.confirmation import (
        confirm_action as _confirm,
        verify_confirmation_token,
    )

    settings = get_settings()
    if not verify_confirmation_token(action_id, body.token, settings.actions_hmac_secret):
        raise HTTPException(status_code=400, detail="Invalid confirmation token.")

    await _get_action_for_user(db, action_id, current_user.id)
    try:
        updated = await _confirm(db, action_id=action_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _build_response(updated)


@router.post("/{action_id}/cancel", response_model=ActionResponse)
async def cancel_action(
    action_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> ActionResponse:
    from prism.services.actions.confirmation import cancel_action as _cancel

    await _get_action_for_user(db, action_id, current_user.id)
    try:
        updated = await _cancel(db, action_id=action_id, user_id=current_user.id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return _build_response(updated)
