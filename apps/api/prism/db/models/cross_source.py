from __future__ import annotations

from datetime import date

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from prism.db.base import Base


class XSPageDaily(Base):
    """Materialized join of GA4 landing pages + GSC pages, keyed by normalized URL + date.

    Populated nightly by the ``precompute_cross_source_views`` worker. Never
    written to directly — always rebuilt from the raw GA4/GSC tables.
    """

    __tablename__ = "xs_page_daily"
    __table_args__ = (
        UniqueConstraint(
            "property_id", "date", "page_url_normalized",
            name="uq_xs_page_daily",
        ),
        Index("ix_xs_page_daily_property_date", "property_id", "date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False,
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    page_url_normalized: Mapped[str] = mapped_column(String(500), nullable=False)

    # GA4 integer metrics
    sessions: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False,
    )
    users: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False,
    )
    engaged_sessions: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False,
    )
    conversions: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False,
    )

    # GA4 float metrics
    revenue: Mapped[float] = mapped_column(
        Float, default=0.0, server_default=sa.text("0"), nullable=False,
    )
    bounce_rate: Mapped[float] = mapped_column(
        Float, default=0.0, server_default=sa.text("0"), nullable=False,
    )
    avg_session_duration: Mapped[float] = mapped_column(
        Float, default=0.0, server_default=sa.text("0"), nullable=False,
    )

    # GSC integer metrics
    clicks: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False,
    )
    impressions: Mapped[int] = mapped_column(
        Integer, default=0, server_default=sa.text("0"), nullable=False,
    )

    # GSC float metrics
    ctr: Mapped[float] = mapped_column(
        Float, default=0.0, server_default=sa.text("0"), nullable=False,
    )
    avg_position: Mapped[float] = mapped_column(
        Float, default=0.0, server_default=sa.text("0"), nullable=False,
    )
