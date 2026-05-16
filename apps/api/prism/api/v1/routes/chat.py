from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import AsyncGenerator

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from prism.core.errors import NotFoundError
from prism.core.middleware import CurrentUser
from prism.db.models.chat import ChatMessage, ChatSession
from prism.db.models.property import Property, PropertyMember
from prism.db.session import get_db_session, get_session_factory
from prism.core.logging import logger

router = APIRouter(prefix="/chat", tags=["chat"])


# ---------------------------------------------------------------------------
# Request / response schemas
# ---------------------------------------------------------------------------

class CreateSessionRequest(BaseModel):
    property_id: int
    source_scope: str = "all"
    title: str | None = None


class SessionResponse(BaseModel):
    id: int
    property_id: int
    user_id: int
    title: str | None
    source_scope: str
    last_message_at: datetime

    model_config = {"from_attributes": True}


class MessageResponse(BaseModel):
    id: int
    session_id: int
    role: str
    content: str
    source_scope: str

    model_config = {"from_attributes": True}


class SessionDetailResponse(BaseModel):
    id: int
    property_id: int
    user_id: int
    title: str | None
    source_scope: str
    last_message_at: datetime
    messages: list[MessageResponse]

    model_config = {"from_attributes": True}


class SendMessageRequest(BaseModel):
    content: str
    source_scope: str = "all"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _assert_property_access(db: AsyncSession, property_id: int, user_id: int) -> Property:
    """Raise 404 if property doesn't exist, 403 if user has no access."""
    result = await db.execute(select(Property).where(Property.id == property_id))
    prop = result.scalar_one_or_none()
    if prop is None:
        raise NotFoundError("Property not found.")

    # Accept if user is the creator OR is a member
    member_result = await db.execute(
        select(PropertyMember).where(
            PropertyMember.property_id == property_id,
            PropertyMember.user_id == user_id,
        )
    )
    member = member_result.scalar_one_or_none()
    is_creator = prop.linked_by_user_id == user_id

    if member is None and not is_creator:
        raise HTTPException(status_code=403, detail="Access denied to this property.")

    return prop


async def _assert_session_access(db: AsyncSession, session_id: int, user_id: int) -> ChatSession:
    result = await db.execute(
        select(ChatSession).where(ChatSession.id == session_id)
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise NotFoundError("Chat session not found.")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Access denied to this chat session.")
    return session


# ---------------------------------------------------------------------------
# Streaming wrapper — accumulates text and saves assistant message after stream
# ---------------------------------------------------------------------------

async def _stream_and_save(
    session_id: int,
    user_id: int,
    property_id: int,
    content: str,
    source_scope: str,
) -> AsyncGenerator[str, None]:
    from prism.ai.agent import run_agent_streaming

    full_text: list[str] = []

    async for chunk in run_agent_streaming(
        property_id=property_id,
        user_id=user_id,
        session_id=session_id,
        user_message=content,
        source_scope=source_scope,
    ):
        yield chunk
        # Accumulate text_delta chunks so we can persist the full response
        try:
            raw = chunk.strip()
            if raw.startswith("data: "):
                data = json.loads(raw[len("data: "):])
                if data.get("type") == "text_delta":
                    full_text.append(data.get("text", ""))
        except Exception:
            pass

    # Persist the assistant message and update session timestamp
    factory = get_session_factory()
    assistant_msg_id: int | None = None
    try:
        async with factory() as db:
            assistant_msg = ChatMessage(
                session_id=session_id,
                role="assistant",
                content="".join(full_text),
                source_scope=source_scope,
            )
            db.add(assistant_msg)

            result = await db.execute(
                select(ChatSession).where(ChatSession.id == session_id)
            )
            session = result.scalar_one_or_none()
            if session is not None:
                session.last_message_at = datetime.now(UTC)

            await db.commit()
            await db.refresh(assistant_msg)
            assistant_msg_id = assistant_msg.id
    except Exception as exc:
        logger.error(
            "Failed to save assistant message after stream",
            session_id=session_id,
            error=str(exc),
        )

    # Fire memory extraction AFTER assistant message is persisted (correct timing)
    if assistant_msg_id is not None:
        try:
            from prism.workers.tasks import extract_memories_from_chat
            extract_memories_from_chat.delay(
                session_id=session_id,
                message_id=assistant_msg_id,
            )
        except Exception:
            pass  # Non-fatal


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@router.post("/sessions", response_model=SessionResponse, status_code=201)
async def create_session(
    body: CreateSessionRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> SessionResponse:
    await _assert_property_access(db, body.property_id, current_user.id)

    session = ChatSession(
        property_id=body.property_id,
        user_id=current_user.id,
        title=body.title,
        source_scope=body.source_scope,
        last_message_at=datetime.now(UTC),
    )
    db.add(session)
    await db.commit()
    await db.refresh(session)
    return SessionResponse.model_validate(session)


@router.get("/sessions", response_model=list[SessionResponse])
async def list_sessions(
    current_user: CurrentUser,
    property_id: int = Query(..., description="Filter by property"),
    db: AsyncSession = Depends(get_db_session),
) -> list[SessionResponse]:
    await _assert_property_access(db, property_id, current_user.id)

    result = await db.execute(
        select(ChatSession)
        .where(
            ChatSession.property_id == property_id,
            ChatSession.user_id == current_user.id,
        )
        .order_by(ChatSession.last_message_at.desc())
        .limit(50)
    )
    sessions = result.scalars().all()
    return [SessionResponse.model_validate(s) for s in sessions]


@router.get("/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: int,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> SessionDetailResponse:
    session = await _assert_session_access(db, session_id, current_user.id)

    result = await db.execute(
        select(ChatMessage)
        .where(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.id.asc())
    )
    messages = result.scalars().all()

    return SessionDetailResponse(
        id=session.id,
        property_id=session.property_id,
        user_id=session.user_id,
        title=session.title,
        source_scope=session.source_scope,
        last_message_at=session.last_message_at,
        messages=[MessageResponse.model_validate(m) for m in messages],
    )


@router.post("/sessions/{session_id}/messages")
async def send_message(
    session_id: int,
    body: SendMessageRequest,
    current_user: CurrentUser,
    db: AsyncSession = Depends(get_db_session),
) -> StreamingResponse:
    session = await _assert_session_access(db, session_id, current_user.id)

    # Persist the user message immediately
    user_msg = ChatMessage(
        session_id=session_id,
        role="user",
        content=body.content,
        source_scope=body.source_scope,
    )
    db.add(user_msg)
    session.last_message_at = datetime.now(UTC)
    await db.commit()
    await db.refresh(user_msg)

    return StreamingResponse(
        _stream_and_save(
            session_id=session_id,
            user_id=current_user.id,
            property_id=session.property_id,
            content=body.content,
            source_scope=body.source_scope,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
