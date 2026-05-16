"""Action confirmation service.

Manages the lifecycle of ActionExecution rows:
  create → pending_confirmation → confirmed → executing → succeeded/failed
  or any state → cancelled/expired

Security:
- HMAC-SHA256 confirmation tokens (single-use by status check, not nonce)
- Idempotency keys prevent double-execution on retries
- 10-minute TTL on pending actions
- allow_destructive_actions gate for delete operations
"""
from __future__ import annotations

import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.actions import ActionExecution
from prism.db.models.cwv import PropertySettings

_ACTION_TTL_MINUTES = 10
_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled", "expired"})


# ---------------------------------------------------------------------------
# HMAC token helpers
# ---------------------------------------------------------------------------

def generate_confirmation_token(action_id: int, secret: str) -> str:
    """Generate a HMAC-SHA256 confirmation token for an action."""
    msg = f"confirm:{action_id}".encode()
    return hmac.new(secret.encode(), msg, hashlib.sha256).hexdigest()


def verify_confirmation_token(action_id: int, token: str, secret: str) -> bool:
    """Constant-time comparison of a provided token against the expected value."""
    expected = generate_confirmation_token(action_id, secret)
    return hmac.compare_digest(expected, token)


def generate_idempotency_key(tool_name: str, tool_input: dict) -> str:
    """Deterministic 16-char hex key for (tool_name, tool_input) dedup."""
    payload = json.dumps(
        {"tool": tool_name, "input": tool_input},
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(payload.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# CRUD helpers
# ---------------------------------------------------------------------------

async def create_pending_action(
    db: AsyncSession,
    *,
    tenant_id: int,
    property_id: int,
    user_id: int,
    tool_name: str,
    tool_input: dict,
    chat_message_id: int | None = None,
    requires_confirmation: bool = True,
) -> ActionExecution:
    """Create an ActionExecution in pending_confirmation state.

    Returns the existing non-terminal action if the idempotency key matches.
    """
    idem_key = generate_idempotency_key(tool_name, tool_input)

    # Dedup check
    existing = (await db.execute(
        select(ActionExecution).where(
            ActionExecution.idempotency_key == idem_key,
            ActionExecution.status.not_in(list(_TERMINAL_STATUSES)),
        )
    )).scalar_one_or_none()
    if existing is not None:
        logger.info(
            "Returning existing non-terminal action (idempotency key match)",
            action_id=existing.id, tool_name=tool_name,
        )
        return existing

    action = ActionExecution(
        tenant_id=tenant_id,
        property_id=property_id,
        user_id=user_id,
        chat_message_id=chat_message_id,
        tool_name=tool_name,
        tool_input=tool_input,
        confirmation_required=requires_confirmation,
        status="pending_confirmation",
        idempotency_key=idem_key,
    )
    db.add(action)
    await db.flush()
    await db.refresh(action)
    logger.info(
        "Pending action created",
        action_id=action.id, tool_name=tool_name, property_id=property_id,
    )
    return action


async def confirm_action(
    db: AsyncSession,
    action_id: int,
    user_id: int,
) -> ActionExecution:
    """Confirm a pending action and execute it.

    Raises ValueError if the action is not in a confirmable state.
    """
    action = (await db.execute(
        select(ActionExecution).where(ActionExecution.id == action_id)
    )).scalar_one_or_none()
    if action is None:
        raise ValueError(f"Action {action_id} not found")

    if action.user_id != user_id:
        raise PermissionError("Cannot confirm another user's action")

    if action.status != "pending_confirmation":
        raise ValueError(f"Action {action_id} is in status '{action.status}', not confirmable")

    ttl_cutoff = datetime.now(UTC) - timedelta(minutes=_ACTION_TTL_MINUTES)
    if action.created_at.replace(tzinfo=UTC) < ttl_cutoff:
        action.status = "expired"
        await db.commit()
        raise ValueError(f"Action {action_id} has expired (TTL {_ACTION_TTL_MINUTES} min)")

    action.confirmed_at = datetime.now(UTC)
    action.confirmed_by_user_id = user_id
    action.status = "confirmed"
    await db.commit()

    await _execute_action(action, db)
    return action


async def cancel_action(
    db: AsyncSession,
    action_id: int,
    user_id: int,
) -> ActionExecution:
    """Cancel a pending action."""
    action = (await db.execute(
        select(ActionExecution).where(ActionExecution.id == action_id)
    )).scalar_one_or_none()
    if action is None:
        raise ValueError(f"Action {action_id} not found")
    if action.user_id != user_id:
        raise PermissionError("Cannot cancel another user's action")
    if action.status in _TERMINAL_STATUSES:
        raise ValueError(f"Action {action_id} is already terminal: {action.status}")

    action.status = "cancelled"
    await db.commit()
    return action


async def expire_stale_actions(db: AsyncSession) -> int:
    """Mark all pending actions older than TTL as expired.

    Returns the count of expired actions.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=_ACTION_TTL_MINUTES)
    result = await db.execute(
        update(ActionExecution)
        .where(
            ActionExecution.status == "pending_confirmation",
            ActionExecution.created_at < cutoff,
        )
        .values(status="expired")
    )
    await db.commit()
    count = result.rowcount
    if count:
        logger.info("Expired stale actions", count=count)
    return count


# ---------------------------------------------------------------------------
# Execution dispatcher
# ---------------------------------------------------------------------------

async def _stub_gsc_submit(tool_input: dict) -> dict:
    """Stub for GSC sitemap submit — replace with real GSC API call."""
    sitemap_url = tool_input.get("sitemap_url", "")
    logger.info("STUB: GSC sitemap submit", sitemap_url=sitemap_url)
    return {"success": True, "message": f"Sitemap {sitemap_url} submitted (stub)"}


async def _stub_gsc_delete(tool_input: dict) -> dict:
    """Stub for GSC sitemap delete — replace with real GSC API call."""
    sitemap_url = tool_input.get("sitemap_url", "")
    logger.info("STUB: GSC sitemap delete", sitemap_url=sitemap_url)
    return {"success": True, "message": f"Sitemap {sitemap_url} deleted (stub)"}


async def _execute_action(action: ActionExecution, db: AsyncSession) -> None:
    """Execute the action and update its status.

    Dispatches to the appropriate stub/service based on tool_name.
    Commits the final status unconditionally.
    """
    action.status = "executing"
    action.executed_at = datetime.now(UTC)
    await db.commit()

    try:
        if action.tool_name == "gsc_submit_sitemap":
            result = await _stub_gsc_submit(action.tool_input)

        elif action.tool_name == "gsc_delete_sitemap":
            # Check destructive action gate
            settings_row = (await db.execute(
                select(PropertySettings).where(
                    PropertySettings.property_id == action.property_id
                )
            )).scalar_one_or_none()
            if settings_row and not settings_row.allow_destructive_actions:
                raise ValueError(
                    "Destructive actions are disabled for this property. "
                    "Enable them in Settings before deleting sitemaps."
                )
            result = await _stub_gsc_delete(action.tool_input)

        else:
            raise ValueError(f"Unknown action tool: {action.tool_name!r}")

        action.status = "succeeded"
        action.result = result

    except Exception as exc:
        action.status = "failed"
        action.error = str(exc)[:500]
        logger.error(
            "Action execution failed",
            action_id=action.id, tool_name=action.tool_name, error=str(exc),
        )

    await db.commit()
