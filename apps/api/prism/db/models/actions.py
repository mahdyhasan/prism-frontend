"""ActionExecution model — audit trail for all mutating agent actions."""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    ForeignKey,
    Index,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from prism.db.base import Base


class ActionExecution(Base):
    """One mutating action proposed by the agent, pending user confirmation.

    Lifecycle: pending_confirmation → confirmed → executing → succeeded/failed
    Side-exits: cancelled (user cancels), expired (10-min TTL exceeded).

    confirmed_by_user_id uses no FK intentionally — audit rows must survive
    even if the approving user account is later deleted.
    """

    __tablename__ = "action_executions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_action_executions_idem_key"),
        Index("ix_action_executions_property_status", "property_id", "status"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenants.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    user_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False, index=True,
    )
    chat_message_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("chat_messages.id", ondelete="SET NULL"),
        nullable=True,
    )
    tool_name: Mapped[str] = mapped_column(String(100), nullable=False)
    tool_input: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        comment="The exact input dict passed to the tool",
    )
    confirmation_required: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.text("1"), nullable=False,
    )
    confirmed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    confirmed_by_user_id: Mapped[int | None] = mapped_column(
        BigInteger, nullable=True,
        comment="No FK — audit row must survive user deletion",
    )
    executed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(30),
        default="pending_confirmation",
        server_default="pending_confirmation",
        nullable=False,
        comment=(
            "pending_confirmation | confirmed | executing | "
            "succeeded | failed | cancelled | expired"
        ),
    )
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(
        String(64), nullable=False,
        comment="SHA-256 of (tool_name + sorted tool_input) — prevents double-execution",
    )
