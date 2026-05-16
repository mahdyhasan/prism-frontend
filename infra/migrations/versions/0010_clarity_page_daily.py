"""Phase D2 — Clarity Data Export API ingestion

Revision ID: 0010
Revises: 0009
Create Date: 2026-05-13

Adds the Clarity API token column to properties and creates the new
clarity_page_daily table that stores per-URL daily frustration signals
(dead clicks, rage clicks, quick backs, scroll depth) pulled from the
Microsoft Clarity Data Export API.

The frustration_score column is not stored — it is computed at query time
as (dead_clicks + 2*rage_clicks + quick_backs) / session_count so that the
weights can be tuned without a migration.

Both additions are guarded with _has_column / _has_table so partial runs
can be retried safely.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels = None
depends_on = None

_TBL = dict(
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_0900_ai_ci",
)


def _has_column(conn, table: str, column: str) -> bool:
    return any(c["name"] == column for c in sa.inspect(conn).get_columns(table))


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def upgrade() -> None:
    conn = op.get_bind()

    # ── Clarity API token on properties (encrypted, nullable) ─────────────────
    if not _has_column(conn, "properties", "clarity_api_token_encrypted"):
        op.add_column(
            "properties",
            sa.Column(
                "clarity_api_token_encrypted",
                sa.Text(),
                nullable=True,
                comment="AES-256-GCM encrypted Clarity Data Export API token",
            ),
        )

    # ── clarity_page_daily ────────────────────────────────────────────────────
    # One row per (property, date, page_url).  page_url is limited to
    # VARCHAR(500) to keep the composite unique key under MySQL's 3072-byte
    # limit in utf8mb4.
    if not _has_table(conn, "clarity_page_daily"):
        op.create_table(
            "clarity_page_daily",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("property_id", sa.BigInteger(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("page_url", sa.String(500), nullable=False),
            # Raw Clarity metrics
            sa.Column("session_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("dead_clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("rage_clicks", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("quick_backs", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("scroll_depth_avg", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "property_id", "date", "page_url",
                name="uq_clarity_page_daily",
            ),
            **_TBL,
        )
        op.create_index(
            "ix_clarity_page_daily_property_date",
            "clarity_page_daily",
            ["property_id", "date"],
        )


def downgrade() -> None:
    op.drop_table("clarity_page_daily")
    op.drop_column("properties", "clarity_api_token_encrypted")
