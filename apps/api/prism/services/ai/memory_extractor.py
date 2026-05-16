"""Memory extraction service.

After each complete user + assistant exchange in a chat session, this service
calls Claude Haiku with the memory_extractor.md prompt to decide what (if
anything) is worth saving to long-term ChatMemory. It also updates the status
of existing memories when the user confirms or rejects prior hypotheses.

Design:
- Cheap model (Haiku) — runs after every exchange, zero user-facing latency.
- Conservative filter — most turns produce zero memories.
- Dedup-aware — loads up to 30 existing memories to avoid re-saving the same
  fact under a slightly different wording.
"""
from __future__ import annotations

import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.logging import logger
from prism.db.models.chat import ChatMemory, ChatMessage, ChatSession
from prism.db.session import get_session_factory
from prism.services.ai.client import CHEAP_MODEL, call_claude

_ALLOWED_KINDS = frozenset({
    "goal", "decision", "hypothesis",
    "business_context", "preference", "recurring_concern",
})

_UPDATE_STATUS_MAP = {
    "confirmed": "active",
    "rejected": "superseded",
    "partially_confirmed": "active",
    "superseded": "superseded",
}


def _load_extractor_prompt() -> str:
    path = Path(__file__).parent.parent.parent / "ai" / "prompts" / "memory_extractor.md"
    return path.read_text(encoding="utf-8")


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = re.sub(r"^```(?:json)?\n?", "", t)
        t = re.sub(r"\n?```$", "", t.strip())
    return t.strip()


async def _apply_extractions(
    result: dict,
    property_id: int,
    db: AsyncSession,
) -> int:
    """Apply the extractor output to the ChatMemory table.

    Returns the total number of memory operations performed.
    """
    ops = 0

    for item in result.get("memories_to_save", []):
        kind = item.get("kind", "")
        text = (item.get("text") or "").strip()
        if not text or kind not in _ALLOWED_KINDS:
            continue

        tags: list = item.get("tags") or []
        confidence: str = item.get("confidence", "explicit")
        supersedes_id: int | None = item.get("supersedes_memory_id")
        expires_after: int | None = item.get("expires_after_days")

        expires_at: datetime | None = None
        if expires_after and isinstance(expires_after, int) and expires_after > 0:
            expires_at = datetime.now(UTC) + timedelta(days=expires_after)

        # Supersede the old memory (only if it belongs to the same property)
        if supersedes_id:
            old = (await db.execute(
                select(ChatMemory).where(
                    ChatMemory.id == supersedes_id,
                    ChatMemory.property_id == property_id,
                )
            )).scalar_one_or_none()
            if old is not None:
                old.status = "superseded"

        db.add(ChatMemory(
            property_id=property_id,
            kind=kind,
            text=text,
            tags=tags,
            confidence=confidence,
            status="active",
            supersedes_id=supersedes_id,
            expires_at=expires_at,
        ))
        ops += 1

    for update in result.get("memories_to_update", []):
        try:
            mid = int(update.get("memory_id", 0))
        except (TypeError, ValueError):
            continue

        new_status_key: str = update.get("new_status", "")
        note: str = (update.get("note") or "").strip()

        if mid <= 0 or new_status_key not in _UPDATE_STATUS_MAP:
            continue

        memory = (await db.execute(
            select(ChatMemory).where(
                ChatMemory.id == mid,
                ChatMemory.property_id == property_id,
            )
        )).scalar_one_or_none()
        if memory is None:
            continue

        memory.status = _UPDATE_STATUS_MAP[new_status_key]
        if note:
            memory.text = f"{memory.text} [{note}]"
        ops += 1

    await db.commit()
    return ops


async def extract_memories_async(
    session_id: int,
    trigger_message_id: int | None = None,
) -> dict:
    """Extract memories from a completed chat exchange.

    Args:
        session_id: The chat session to inspect.
        trigger_message_id: The user message ID that kicked off the exchange.
            When provided, fetches that message + the next assistant message.
            When omitted, fetches the last 2 messages (user + assistant).

    Returns a dict with keys: session_id, memories_saved, memories_updated.
    Returns {"skipped": reason} when extraction is not applicable.
    """
    factory = get_session_factory()

    async with factory() as db:
        session = (await db.execute(
            select(ChatSession).where(ChatSession.id == session_id)
        )).scalar_one_or_none()
        if session is None:
            return {"error": f"Session {session_id} not found"}

        property_id: int = session.property_id

        # Fetch the exchange messages
        if trigger_message_id is not None:
            msgs_result = await db.execute(
                select(ChatMessage)
                .where(
                    ChatMessage.session_id == session_id,
                    ChatMessage.id >= trigger_message_id,
                )
                .order_by(ChatMessage.id.asc())
                .limit(2)
            )
        else:
            msgs_result = await db.execute(
                select(ChatMessage)
                .where(ChatMessage.session_id == session_id)
                .order_by(ChatMessage.id.desc())
                .limit(2)
            )

        exchange = list(msgs_result.scalars().all())

        # When fetching desc we need to reverse so user comes before assistant
        if trigger_message_id is None:
            exchange.sort(key=lambda m: m.id)

        if len(exchange) < 2:
            return {"skipped": "incomplete exchange — assistant has not responded yet"}

        user_msg = next((m for m in exchange if m.role == "user"), None)
        assistant_msg = next((m for m in exchange if m.role == "assistant"), None)

        if user_msg is None or assistant_msg is None:
            return {"skipped": "missing user or assistant role in exchange"}

        # Existing memories for dedup context
        existing_result = await db.execute(
            select(ChatMemory)
            .where(
                ChatMemory.property_id == property_id,
                ChatMemory.status == "active",
            )
            .order_by(ChatMemory.id.desc())
            .limit(30)
        )
        existing_memories = [
            {"id": m.id, "kind": m.kind, "text": m.text, "tags": m.tags or []}
            for m in existing_result.scalars().all()
        ]

        # Tool calls summary
        tool_summary: list[str] = []
        tc = assistant_msg.tool_calls_json
        if isinstance(tc, list):
            for entry in tc[:5]:
                if isinstance(entry, dict):
                    tool_summary.append(entry.get("name", "unknown"))

        # Tenant ID for logging
        from prism.db.models.property import Property
        prop = (await db.execute(
            select(Property).where(Property.id == property_id)
        )).scalar_one_or_none()
        tenant_id: int = prop.tenant_id if prop else 0

        payload_text = (
            f"user_message: {user_msg.content[:2000]}\n\n"
            f"assistant_message: {assistant_msg.content[:2000]}\n\n"
            f"tool_calls_summary: {', '.join(tool_summary) or 'none'}\n\n"
            f"existing_memories: {json.dumps(existing_memories, ensure_ascii=False)}\n\n"
            f"property_id: {property_id}"
        )

        system_prompt = _load_extractor_prompt()

        try:
            response_text = await call_claude(
                purpose="memory.extract",
                model=CHEAP_MODEL,
                system=system_prompt,
                messages=[{"role": "user", "content": payload_text}],
                max_tokens=1024,
                db=db,
                tenant_id=tenant_id,
                property_id=property_id,
            )
        except Exception as exc:
            logger.error(
                "Memory extraction Claude call failed",
                session_id=session_id,
                error=str(exc),
            )
            return {"error": str(exc)}

        cleaned = _strip_fences(response_text)
        try:
            result = json.loads(cleaned)
        except (json.JSONDecodeError, ValueError):
            logger.warning(
                "Memory extractor returned unparseable JSON",
                session_id=session_id,
                preview=response_text[:150],
            )
            return {"skipped": "json_parse_error"}

        ops = await _apply_extractions(result, property_id, db)

    saved = len(result.get("memories_to_save", []))
    updated = len(result.get("memories_to_update", []))

    logger.info(
        "Memory extraction complete",
        session_id=session_id,
        memories_saved=saved,
        memories_updated=updated,
        ops=ops,
    )
    return {
        "session_id": session_id,
        "memories_saved": saved,
        "memories_updated": updated,
    }
