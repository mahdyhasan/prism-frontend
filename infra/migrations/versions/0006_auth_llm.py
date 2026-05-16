"""Add password_hash to users; add property_llm_configs table

Revision ID: 0006
Revises: 0005
Create Date: 2026-05-12
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0006"
down_revision: str | None = "0005"
branch_labels = None
depends_on = None

_TBL = dict(mysql_engine="InnoDB", mysql_charset="utf8mb4", mysql_collate="utf8mb4_0900_ai_ci")
_NOW = sa.text("NOW()")


def upgrade() -> None:
    # ── password_hash on users ────────────────────────────────────────────────
    op.add_column(
        "users",
        sa.Column("password_hash", sa.String(255), nullable=True),
    )

    # ── property_llm_configs ──────────────────────────────────────────────────
    op.create_table(
        "property_llm_configs",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("property_id", sa.BigInteger(), nullable=False),
        sa.Column("llm_provider", sa.String(50), nullable=False, server_default="anthropic"),
        sa.Column("llm_model", sa.String(100), nullable=False, server_default="claude-sonnet-4-6"),
        sa.Column("llm_api_key_encrypted", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=_NOW, nullable=False),
        sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("property_id", name="uq_property_llm_config"),
        **_TBL,
    )
    op.create_index(
        "ix_property_llm_configs_property_id",
        "property_llm_configs",
        ["property_id"],
    )


def downgrade() -> None:
    op.drop_table("property_llm_configs")
    op.drop_column("users", "password_hash")
