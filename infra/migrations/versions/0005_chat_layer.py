"""Chat layer, xs_page_daily, pinned questions, daily briefs

Revision ID: 0005
Revises: 0004
Create Date: 2026-05-11
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import mysql as mysql_dialect

revision: str = "0005"
down_revision: str | None = "0004"
branch_labels = None
depends_on = None

_TBL = dict(mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci")
_NOW = sa.text("NOW()")


def upgrade() -> None:
    # ── xs_page_daily ─────────────────────────────────────────────────────────
    # Materialized cross-source join: GA4 landing pages + GSC pages per URL/date.
    # IMPORTANT: page_url_normalized is VARCHAR(500) — 500*4=2000 bytes < 3072 InnoDB limit.
    op.create_table(
        "xs_page_daily",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("page_url_normalized", sa.String(500), nullable=False),
        # GA4 integer metrics
        sa.Column("sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("users", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("engaged_sessions", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("conversions", sa.Integer(), nullable=False, server_default="0"),
        # GA4 float metrics
        sa.Column("revenue", sa.Float(), nullable=False, server_default="0"),
        sa.Column("bounce_rate", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_session_duration", sa.Float(), nullable=False, server_default="0"),
        # GSC integer metrics
        sa.Column("clicks", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("impressions", sa.Integer(), nullable=False, server_default="0"),
        # GSC float metrics
        sa.Column("ctr", sa.Float(), nullable=False, server_default="0"),
        sa.Column("avg_position", sa.Float(), nullable=False, server_default="0"),
        # Base cols
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "date", "page_url_normalized", name="uq_xs_page_daily"),
        **_TBL,
    )
    op.create_index("ix_xs_page_daily_property_date", "xs_page_daily", ["property_id", "date"])

    # ── chat_sessions ─────────────────────────────────────────────────────────
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(500), nullable=True),
        sa.Column("source_scope", sa.String(20), nullable=False, server_default="all"),
        sa.Column("last_message_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **_TBL,
    )
    op.create_index("ix_chat_sessions_property_id", "chat_sessions", ["property_id"])
    op.create_index("ix_chat_sessions_user_id", "chat_sessions", ["user_id"])

    # ── chat_messages ─────────────────────────────────────────────────────────
    # content is LONGTEXT (4GB max) — stores full assistant responses with tool citations.
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("session_id", sa.BigInteger(), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(length=4294967295), nullable=False),  # LONGTEXT
        sa.Column("tool_calls_json", sa.JSON(), nullable=True),
        sa.Column("source_scope", sa.String(20), nullable=False, server_default="all"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["chat_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **_TBL,
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])

    # ── chat_memories ─────────────────────────────────────────────────────────
    # Must be created before the self-referential FK can be added.
    op.create_table(
        "chat_memories",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.String(10), nullable=False, server_default="explicit"),
        sa.Column("status", sa.String(20), nullable=False, server_default="active"),
        sa.Column("supersedes_id", sa.BigInteger(), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        # Self-referential FK added after table creation (see below)
        sa.PrimaryKeyConstraint("id"),
        **_TBL,
    )
    # Add self-referential FK separately to avoid MySQL issues with forward references
    op.create_foreign_key(
        "fk_chat_memories_supersedes",
        "chat_memories", "chat_memories",
        ["supersedes_id"], ["id"],
        ondelete="SET NULL",
    )
    op.create_index("ix_chat_memories_property_status", "chat_memories", ["property_id", "status"])

    # ── pinned_questions ──────────────────────────────────────────────────────
    op.create_table(
        "pinned_questions",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("user_id", sa.BigInteger(), nullable=False),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("source_scope", sa.String(20), nullable=False, server_default="all"),
        sa.Column("date_range_strategy", sa.String(20), nullable=False, server_default="rolling_28d"),
        sa.Column("tags", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **_TBL,
    )
    op.create_index("ix_pinned_questions_property_id", "pinned_questions", ["property_id"])

    # ── pinned_question_runs ──────────────────────────────────────────────────
    op.create_table(
        "pinned_question_runs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pin_id", sa.BigInteger(), nullable=False),
        sa.Column("run_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("answer_json", sa.Text(length=4294967295), nullable=True),  # LONGTEXT
        sa.Column("run_status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["pin_id"], ["pinned_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        **_TBL,
    )
    op.create_index("ix_pinned_question_runs_pin_id", "pinned_question_runs", ["pin_id"])

    # ── daily_briefs ──────────────────────────────────────────────────────────
    op.create_table(
        "daily_briefs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("brief_date", sa.Date(), nullable=False),
        sa.Column("brief_json", sa.Text(length=4294967295), nullable=True),  # LONGTEXT
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("generation_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", "brief_date", name="uq_daily_briefs_property_date"),
        **_TBL,
    )
    op.create_index("ix_daily_briefs_property_id", "daily_briefs", ["property_id"])


def downgrade() -> None:
    op.drop_table("daily_briefs")
    op.drop_table("pinned_question_runs")
    op.drop_table("pinned_questions")
    op.drop_constraint("fk_chat_memories_supersedes", "chat_memories", type_="foreignkey")
    op.drop_table("chat_memories")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")
    op.drop_table("xs_page_daily")
