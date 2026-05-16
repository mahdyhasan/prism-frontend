from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from prism.db.models.chat import ChatMemory, PinnedQuestion
from prism.db.models.property import Property
from prism.ai.tools.schemas import (
    GetPropertyMetaInput,
    ListPinnedInput,
    RecallMemoryInput,
    SaveMemoryInput,
)

# ---------------------------------------------------------------------------
# recall_memory
# ---------------------------------------------------------------------------

async def recall_memory(inp: RecallMemoryInput, db: AsyncSession) -> dict[str, Any]:
    stmt = (
        select(ChatMemory)
        .where(
            ChatMemory.property_id == inp.property_id,
            ChatMemory.status == "active",
        )
        .order_by(ChatMemory.created_at.desc())
        .limit(inp.limit * 5)  # Over-fetch then filter in Python for text search
    )
    result = await db.execute(stmt)
    all_memories = result.scalars().all()

    # Simple text search: match query words against text and tags
    query_lower = inp.query.lower()
    query_words = set(query_lower.split())

    def _matches(mem: ChatMemory) -> bool:
        if query_lower in (mem.text or "").lower():
            return True
        tags = mem.tags or []
        tag_text = " ".join(str(t).lower() for t in tags)
        for word in query_words:
            if word in tag_text:
                return True
        return False

    matched = [m for m in all_memories if _matches(m)]
    matched = matched[: inp.limit]

    memories: list[dict[str, Any]] = []
    for m in matched:
        memories.append({
            "id": m.id,
            "kind": m.kind,
            "text": m.text,
            "tags": m.tags or [],
            "confidence": m.confidence,
            "created_at": m.created_at.isoformat() if m.created_at else None,
        })

    return {"memories": memories}


# ---------------------------------------------------------------------------
# save_memory
# ---------------------------------------------------------------------------

async def save_memory(inp: SaveMemoryInput, db: AsyncSession) -> dict[str, Any]:
    expires_at: datetime | None = None
    if inp.expires_after_days is not None:
        expires_at = datetime.now(tz=timezone.utc) + timedelta(days=inp.expires_after_days)

    new_memory = ChatMemory(
        property_id=inp.property_id,
        kind=inp.kind,
        text=inp.text,
        tags=inp.tags if inp.tags else [],
        confidence=inp.confidence,
        status="active",
        expires_at=expires_at,
    )

    if inp.supersedes_memory_id is not None:
        # Mark old memory as superseded
        await db.execute(
            update(ChatMemory)
            .where(
                ChatMemory.id == inp.supersedes_memory_id,
                ChatMemory.property_id == inp.property_id,
            )
            .values(status="superseded")
        )
        new_memory.supersedes_id = inp.supersedes_memory_id

    db.add(new_memory)
    await db.flush()  # Populate id without committing
    await db.commit()

    return {"id": new_memory.id, "success": True}


# ---------------------------------------------------------------------------
# list_pinned_questions
# ---------------------------------------------------------------------------

async def list_pinned_questions(inp: ListPinnedInput, db: AsyncSession) -> dict[str, Any]:
    stmt = (
        select(PinnedQuestion)
        .where(PinnedQuestion.property_id == inp.property_id)
        .order_by(PinnedQuestion.updated_at.desc())
    )
    result = await db.execute(stmt)
    pins = result.scalars().all()

    pin_list: list[dict[str, Any]] = []
    for p in pins:
        pin_list.append({
            "id": p.id,
            "title": p.title,
            "prompt": p.prompt,
            "scope": p.source_scope,
            "date_range_strategy": p.date_range_strategy,
            "tags": p.tags or [],
            "created_at": p.created_at.isoformat() if p.created_at else None,
        })

    return {"pins": pin_list}


# ---------------------------------------------------------------------------
# get_property_metadata
# ---------------------------------------------------------------------------

# Hardcoded Augmex constants — will be made configurable per-property later
_FOCUS_PAGES: list[str] = [
    "/staff-augmentation",
    "/services/*",
    "/contact",
    "/case-studies/*",
]

_PRIMARY_CONVERSIONS: list[str] = [
    "contact_form",
    "calendar_booking",
]


async def get_property_metadata(inp: GetPropertyMetaInput, db: AsyncSession) -> dict[str, Any]:
    stmt = select(Property).where(Property.id == inp.property_id)
    result = await db.execute(stmt)
    prop = result.scalar_one_or_none()

    if prop is None:
        return {"error": f"Property {inp.property_id} not found"}

    ga4_linked = bool(prop.ga4_property_id)
    gsc_linked = bool(prop.gsc_site_url)

    # Derive domain from gsc_site_url if available, otherwise from display_name
    domain: str | None = None
    if prop.gsc_site_url:
        url = prop.gsc_site_url.rstrip("/")
        domain = url.replace("sc-domain:", "").replace("https://", "").replace("http://", "").split("/")[0]

    # Prefer the per-property list set in Settings; fall back to baked-in
    # defaults for legacy properties that haven't configured this yet.
    primary_conversions = prop.primary_conversion_events or _PRIMARY_CONVERSIONS

    return {
        "id": prop.id,
        "display_name": prop.display_name,
        "domain": domain,
        "timezone": prop.timezone,
        "ga4_linked": ga4_linked,
        "gsc_linked": gsc_linked,
        "gsc_site_url": prop.gsc_site_url,
        "focus_pages": _FOCUS_PAGES,
        "primary_conversions": primary_conversions,
    }
