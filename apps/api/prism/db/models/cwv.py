"""Core Web Vitals DB models.

Three models:
- PropertySettings  per-property CWV audit configuration (property_id is PK)
- CWVPageAudit      one row per (property, url, strategy, audit run)
- CWVOriginAudit    one row per (property, origin, strategy, audit run)
"""
from __future__ import annotations

from datetime import datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from prism.db.base import Base

_TBL = {
    "mysql_engine": "InnoDB",
    "mysql_charset": "utf8mb4",
    "mysql_collate": "utf8mb4_0900_ai_ci",
}


# ---------------------------------------------------------------------------
# PropertySettings — 1:1 with Property, property_id IS the primary key
# ---------------------------------------------------------------------------

class _NoPKBase(DeclarativeBase):
    """Minimal declarative base for tables with a natural primary key.

    Shares the same metadata as Base so Alembic autogenerate sees all tables.
    """
    metadata = Base.metadata  # type: ignore[assignment]


class PropertySettings(_NoPKBase):
    """Per-property settings for CWV audits and destructive-action gating."""

    __tablename__ = "property_settings"
    __table_args__ = ({"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},)

    property_id: Mapped[int] = mapped_column(
        BigInteger,
        ForeignKey("properties.id", ondelete="CASCADE"),
        primary_key=True,
    )
    allow_destructive_actions: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False,
    )
    cwv_audit_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.text("1"), nullable=False,
    )
    cwv_audit_frequency_hours: Mapped[int] = mapped_column(
        Integer, default=24, server_default=sa.text("24"), nullable=False,
    )
    cwv_top_pages_count: Mapped[int] = mapped_column(
        Integer, default=25, server_default=sa.text("25"), nullable=False,
        comment="How many top-traffic pages to audit per run",
    )
    cwv_mobile_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.text("1"), nullable=False,
    )
    cwv_desktop_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=sa.text("1"), nullable=False,
    )
    psi_api_key_encrypted: Mapped[str | None] = mapped_column(
        Text, nullable=True,
        comment="AES-256-GCM encrypted PageSpeed Insights API key",
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=sa.text("NOW()"),
        onupdate=sa.text("NOW()"),
        nullable=False,
    )


# ---------------------------------------------------------------------------
# CWVPageAudit — one PSI/CrUX audit result per (property, url, strategy)
# ---------------------------------------------------------------------------

class CWVPageAudit(Base):
    """One PSI or CrUX audit result for a specific page and strategy."""

    __tablename__ = "cwv_page_audits"
    __table_args__ = (
        Index(
            "ix_cwv_page_audits_prop_url_strategy_at",
            "property_id", "url_normalized", "strategy", "audited_at",
        ),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    audited_url: Mapped[str] = mapped_column(
        String(1024), nullable=False,
        comment="Full URL as audited (may include scheme + domain)",
    )
    url_normalized: Mapped[str] = mapped_column(
        String(1024), nullable=False,
        comment="Path-only normalized URL for joining with xs_page_daily",
    )
    strategy: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="'mobile' or 'desktop'",
    )
    audited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        comment="UTC timestamp of the audit run",
    )
    source: Mapped[str] = mapped_column(
        String(10), nullable=False, default="psi",
        comment="'psi' (PageSpeed Insights) or 'crux' (Chrome UX Report)",
    )
    lcp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cls: Mapped[float | None] = mapped_column(Float, nullable=True)
    fcp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttfb_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lighthouse_performance_score: Mapped[int | None] = mapped_column(
        Integer, nullable=True,
        comment="Lighthouse perf score 0-100 (PSI lab data only)",
    )
    field_data_available: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False,
    )
    lab_data_available: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False,
    )
    cwv_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="insufficient_data",
        comment="good | needs_improvement | poor | insufficient_data",
    )
    opportunities: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Top PSI Lighthouse opportunities array",
    )
    diagnostics: Mapped[dict | None] = mapped_column(
        JSON, nullable=True,
        comment="Top PSI Lighthouse diagnostics array",
    )


# ---------------------------------------------------------------------------
# CWVOriginAudit — origin-level CrUX data
# ---------------------------------------------------------------------------

class CWVOriginAudit(Base):
    """Origin-level CrUX field data for an entire domain."""

    __tablename__ = "cwv_origin_audits"
    __table_args__ = (
        Index(
            "ix_cwv_origin_audits_prop_strategy_at",
            "property_id", "strategy", "audited_at",
        ),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"),
        nullable=False, index=True,
    )
    origin: Mapped[str] = mapped_column(
        String(255), nullable=False,
        comment="e.g. 'https://augmex.io'",
    )
    strategy: Mapped[str] = mapped_column(
        String(10), nullable=False,
        comment="'mobile', 'desktop', or 'all'",
    )
    audited_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
    )
    lcp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    inp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cls: Mapped[float | None] = mapped_column(Float, nullable=True)
    fcp_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    ttfb_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cwv_status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="insufficient_data",
    )
    field_data_available: Mapped[bool] = mapped_column(
        Boolean, default=False, server_default=sa.text("0"), nullable=False,
    )
