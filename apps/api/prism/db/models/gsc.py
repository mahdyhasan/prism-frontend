from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prism.db.base import Base


class GSCQueriesDaily(Base):
    """Per-day search query metrics broken down by country and device."""

    __tablename__ = "gsc_queries_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "query", "country", "device", name="uq_gsc_queries_daily"),
        Index("ix_gsc_queries_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    query: Mapped[str] = mapped_column(String(500), nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    device: Mapped[str] = mapped_column(String(50), nullable=False)

    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class GSCPagesDaily(Base):
    """Per-day landing page metrics from Search Console."""

    __tablename__ = "gsc_pages_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "page", name="uq_gsc_pages_daily"),
        Index("ix_gsc_pages_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    page: Mapped[str] = mapped_column(String(700), nullable=False)

    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class GSCQueryPageDaily(Base):
    """Per-day query+page join — for opportunity analysis (which page ranks for which query)."""

    __tablename__ = "gsc_query_page_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "query", "page", name="uq_gsc_query_page_daily"),
        Index("ix_gsc_query_page_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    query: Mapped[str] = mapped_column(String(250), nullable=False)
    page: Mapped[str] = mapped_column(String(250), nullable=False)

    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class GSCAppearanceDaily(Base):
    """Per-day searchAppearance dimension (rich result types: AMP_BLUE_LINK, RICHCARD, etc.)."""

    __tablename__ = "gsc_appearance_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "search_appearance", name="uq_gsc_appearance_daily"),
        Index("ix_gsc_appearance_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    search_appearance: Mapped[str] = mapped_column(String(100), nullable=False)

    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class GSCSearchTypeDaily(Base):
    """Per-day breakdown by GSC search type (web, image, video, news, googleNews, discover)."""

    __tablename__ = "gsc_search_type_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "search_type", name="uq_gsc_search_type_daily"),
        Index("ix_gsc_search_type_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    search_type: Mapped[str] = mapped_column(String(20), nullable=False)

    clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    impressions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    ctr: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    position: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
