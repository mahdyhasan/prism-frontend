"""Phase 2I-B — Actions layer (mutating tools with confirmation flow)

Revision ID: 0012
Revises: 0011
Create Date: 2026-05-15

Creates:
- action_executions    Every mutating action the agent proposes, with full
                       audit trail from pending_confirmation through execution.

Guarded with _has_table so partial runs can be retried safely.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0012"
down_revision: str | None = "0011"
branch_labels = None
depends_on = None

_TBL = dict(
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_0900_ai_ci",
)


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def upgrade() -> None:
    conn = op.get_bind()

    if not _has_table(conn, "action_executions"):
        op.create_table(
            "action_executions",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("tenant_id", sa.BigInteger(), nullable=False),
            sa.Column("property_id", sa.BigInteger(), nullable=False),
            sa.Column("user_id", sa.BigInteger(), nullable=False),
            sa.Column("chat_message_id", sa.BigInteger(), nullable=True),
            sa.Column("tool_name", sa.String(100), nullable=False),
            sa.Column("tool_input", sa.JSON(), nullable=False),
            sa.Column("confirmation_required", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("confirmed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("confirmed_by_user_id", sa.BigInteger(), nullable=True,
                      comment="No FK — audit row must survive user deletion"),
            sa.Column("executed_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column(
                "status", sa.String(30), nullable=False,
                server_default="pending_confirmation",
                comment="pending_confirmation|confirmed|executing|succeeded|failed|cancelled|expired",
            ),
            sa.Column("result", sa.JSON(), nullable=True),
            sa.Column("error", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name="fk_action_exec_tenant", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"], name="fk_action_exec_property", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["user_id"], ["users.id"], name="fk_action_exec_user", ondelete="RESTRICT"),
            sa.ForeignKeyConstraint(["chat_message_id"], ["chat_messages.id"], name="fk_action_exec_msg", ondelete="SET NULL"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("idempotency_key", name="uq_action_executions_idem_key"),
            **_TBL,
        )
        op.create_index("ix_action_executions_tenant_id", "action_executions", ["tenant_id"])
        op.create_index("ix_action_executions_property_id", "action_executions", ["property_id"])
        op.create_index("ix_action_executions_user_id", "action_executions", ["user_id"])
        op.create_index(
            "ix_action_executions_property_status",
            "action_executions",
            ["property_id", "status"],
        )


def downgrade() -> None:
    op.drop_table("action_executions")
