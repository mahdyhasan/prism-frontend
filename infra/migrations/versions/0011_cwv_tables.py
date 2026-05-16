"""Phase 2I-A — Core Web Vitals data layer

Revision ID: 0011
Revises: 0010
Create Date: 2026-05-15

Creates three tables:
- property_settings    Per-property CWV audit config + destructive-action gate
- cwv_page_audits      PSI/CrUX audit results per (property, url, strategy)
- cwv_origin_audits    CrUX origin-level field data per (property, strategy)

All additions are guarded so partial runs can be retried safely.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0011"
down_revision: str | None = "0010"
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

    # ── property_settings ────────────────────────────────────────────────────
    if not _has_table(conn, "property_settings"):
        op.create_table(
            "property_settings",
            sa.Column("property_id", sa.BigInteger(), nullable=False),
            sa.Column("allow_destructive_actions", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("cwv_audit_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("cwv_audit_frequency_hours", sa.Integer(), nullable=False, server_default=sa.text("24")),
            sa.Column("cwv_top_pages_count", sa.Integer(), nullable=False, server_default=sa.text("25")),
            sa.Column("cwv_mobile_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("cwv_desktop_enabled", sa.Boolean(), nullable=False, server_default=sa.text("1")),
            sa.Column("psi_api_key_encrypted", sa.Text(), nullable=True,
                      comment="AES-256-GCM encrypted PageSpeed Insights API key"),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.ForeignKeyConstraint(
                ["property_id"], ["properties.id"],
                name="fk_property_settings_property_id",
                ondelete="CASCADE",
            ),
            sa.PrimaryKeyConstraint("property_id"),
            **_TBL,
        )

    # ── cwv_page_audits ───────────────────────────────────────────────────────
    if not _has_table(conn, "cwv_page_audits"):
        op.create_table(
            "cwv_page_audits",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("property_id", sa.BigInteger(), nullable=False),
            sa.Column("audited_url", sa.String(1024), nullable=False),
            sa.Column("url_normalized", sa.String(1024), nullable=False),
            sa.Column("strategy", sa.String(10), nullable=False),
            sa.Column("audited_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("source", sa.String(10), nullable=False, server_default="psi"),
            sa.Column("lcp_ms", sa.Integer(), nullable=True),
            sa.Column("inp_ms", sa.Integer(), nullable=True),
            sa.Column("cls", sa.Float(), nullable=True),
            sa.Column("fcp_ms", sa.Integer(), nullable=True),
            sa.Column("ttfb_ms", sa.Integer(), nullable=True),
            sa.Column("lighthouse_performance_score", sa.Integer(), nullable=True),
            sa.Column("field_data_available", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("lab_data_available", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("cwv_status", sa.String(20), nullable=False, server_default="insufficient_data"),
            sa.Column("opportunities", sa.JSON(), nullable=True),
            sa.Column("diagnostics", sa.JSON(), nullable=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            **_TBL,
        )
        op.create_index("ix_cwv_page_audits_property_id", "cwv_page_audits", ["property_id"])
        op.create_index(
            "ix_cwv_page_audits_prop_url_strategy_at",
            "cwv_page_audits",
            ["property_id", "url_normalized", "strategy", "audited_at"],
        )

    # ── cwv_origin_audits ─────────────────────────────────────────────────────
    if not _has_table(conn, "cwv_origin_audits"):
        op.create_table(
            "cwv_origin_audits",
            sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
            sa.Column("property_id", sa.BigInteger(), nullable=False),
            sa.Column("origin", sa.String(255), nullable=False),
            sa.Column("strategy", sa.String(10), nullable=False),
            sa.Column("audited_at", sa.DateTime(timezone=True), nullable=False),
            sa.Column("lcp_ms", sa.Integer(), nullable=True),
            sa.Column("inp_ms", sa.Integer(), nullable=True),
            sa.Column("cls", sa.Float(), nullable=True),
            sa.Column("fcp_ms", sa.Integer(), nullable=True),
            sa.Column("ttfb_ms", sa.Integer(), nullable=True),
            sa.Column("cwv_status", sa.String(20), nullable=False, server_default="insufficient_data"),
            sa.Column("field_data_available", sa.Boolean(), nullable=False, server_default=sa.text("0")),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False),
            sa.ForeignKeyConstraint(["property_id"], ["properties.id"], ondelete="CASCADE"),
            sa.PrimaryKeyConstraint("id"),
            **_TBL,
        )
        op.create_index("ix_cwv_origin_audits_property_id", "cwv_origin_audits", ["property_id"])
        op.create_index(
            "ix_cwv_origin_audits_prop_strategy_at",
            "cwv_origin_audits",
            ["property_id", "strategy", "audited_at"],
        )


def downgrade() -> None:
    op.drop_table("cwv_origin_audits")
    op.drop_table("cwv_page_audits")
    op.drop_table("property_settings")
