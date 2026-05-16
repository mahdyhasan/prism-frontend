"""Phase B v2 — exits column on landing pages + new device cross-dim table

Revision ID: 0009
Revises: 0008
Create Date: 2026-05-13

Adds the `exits` metric to the existing per-page daily rollup, and a new
table that breaks pages out by deviceCategory (mobile/desktop/tablet) so the
Pages dashboard can answer "this page bombs on mobile" questions.

Both columns default to 0 server-side so historical rows pulled before this
migration don't break aggregate queries — they'll just look like 0-exit /
0-device-traffic pages until the user re-syncs.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0009"
down_revision: str | None = "0008"
branch_labels = None
depends_on = None

_TBL = dict(
    mysql_engine="InnoDB",
    mysql_charset="utf8mb4",
    mysql_collate="utf8mb4_0900_ai_ci",
)


def _has_column(conn, table: str, column: str) -> bool:
    inspector = sa.inspect(conn)
    return any(c["name"] == column for c in inspector.get_columns(table))


def _has_table(conn, table: str) -> bool:
    return sa.inspect(conn).has_table(table)


def upgrade() -> None:
    conn = op.get_bind()

    # ── exits on existing landing-pages rollup (idempotent) ───────────────────
    if not _has_column(conn, "ga4_landing_pages_daily", "exits"):
        op.add_column(
            "ga4_landing_pages_daily",
            sa.Column(
                "exits",
                sa.Integer(),
                nullable=False,
                server_default=sa.text("0"),
            ),
        )

    # ── new (landingPage × deviceCategory) daily cross-dim ────────────────────
    # landing_page narrowed to VARCHAR(500) (matches xs_page_daily). With
    # device_category VARCHAR(100) the composite unique key fits well under
    # MySQL's 3072-byte limit in utf8mb4.
    if not _has_table(conn, "ga4_landing_page_device_daily"):
        op.create_table(
            "ga4_landing_page_device_daily",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("property_id", sa.BigInteger(), nullable=False),
            sa.Column("date", sa.Date(), nullable=False),
            sa.Column("landing_page", sa.String(500), nullable=False),
            sa.Column("device_category", sa.String(100), nullable=False),
            sa.Column("sessions", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("users", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("engaged_sessions", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("conversions", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.Column("revenue", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("bounce_rate", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("avg_session_duration", sa.Float(), nullable=False, server_default=sa.text("0")),
            sa.Column("exits", sa.Integer(), nullable=False, server_default=sa.text("0")),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint(
                "property_id", "date", "landing_page", "device_category",
                name="uq_ga4_lp_device_daily",
            ),
            **_TBL,
        )
        op.create_index(
            "ix_ga4_lp_device_daily_property_date",
            "ga4_landing_page_device_daily",
            ["property_id", "date"],
        )


def downgrade() -> None:
    op.drop_table("ga4_landing_page_device_daily")
    op.drop_column("ga4_landing_pages_daily", "exits")
