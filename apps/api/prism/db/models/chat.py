from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prism.db.base import Base

if TYPE_CHECKING:
    pass


class ChatSession(Base):
    """A single conversation thread between a user and the PRISM AI assistant."""

    __tablename__ = "chat_sessions"
    __table_args__ = (
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    title: Mapped[str | None] = mapped_column(String(500), nullable=True)
    source_scope: Mapped[str] = mapped_column(
        String(20), default="all", server_default="all", nullable=False,
    )
    last_message_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False,
    )

    messages: Mapped[list["ChatMessage"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ChatMessage(Base):
    """A single message within a ChatSession, from either the user or the assistant."""

    __tablename__ = "chat_messages"
    __table_args__ = (
        Index("ix_chat_messages_session_id", "session_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    session_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text(length=2**32 - 1), nullable=False)
    tool_calls_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_scope: Mapped[str] = mapped_column(
        String(20), default="all", server_default="all", nullable=False,
    )

    session: Mapped["ChatSession"] = relationship(back_populates="messages")


class ChatMemory(Base):
    """A durable memory item extracted from chat sessions for a property."""

    __tablename__ = "chat_memories"
    __table_args__ = (
        Index("ix_chat_memories_property_status", "property_id", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False,
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)
    confidence: Mapped[str] = mapped_column(
        String(10), default="explicit", server_default="explicit", nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(20), default="active", server_default="active", nullable=False,
    )
    supersedes_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("chat_memories.id", ondelete="SET NULL"), nullable=True,
    )
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PinnedQuestion(Base):
    """A saved prompt that the user wants answered on a recurring schedule."""

    __tablename__ = "pinned_questions"
    __table_args__ = (
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    source_scope: Mapped[str] = mapped_column(
        String(20), default="all", server_default="all", nullable=False,
    )
    date_range_strategy: Mapped[str] = mapped_column(
        String(20), default="rolling_28d", server_default="rolling_28d", nullable=False,
    )
    tags: Mapped[list | None] = mapped_column(JSON, nullable=True)

    runs: Mapped[list["PinnedQuestionRun"]] = relationship(
        back_populates="pin",
        cascade="all, delete-orphan",
    )


class PinnedQuestionRun(Base):
    """A single execution of a PinnedQuestion, storing the answer and run status."""

    __tablename__ = "pinned_question_runs"
    __table_args__ = (
        Index("ix_pinned_question_runs_pin_id", "pin_id"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    pin_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("pinned_questions.id", ondelete="CASCADE"), nullable=False,
    )
    run_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False,
    )
    answer_json: Mapped[str | None] = mapped_column(Text(length=2**32 - 1), nullable=True)
    run_status: Mapped[str] = mapped_column(
        String(20), default="pending", server_default="pending", nullable=False,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    pin: Mapped["PinnedQuestion"] = relationship(back_populates="runs")
