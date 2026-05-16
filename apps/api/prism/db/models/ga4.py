from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Index, Integer, JSON, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prism.db.base import Base


class GA4DailyMetrics(Base):
    """Top-level daily rollup — date only, no additional dimensions."""

    __tablename__ = "ga4_daily_metrics"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "dimension_hash", name="uq_ga4_daily_metrics"),
        Index("ix_ga4_daily_metrics_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    dimension_hash: Mapped[str] = mapped_column(String(64), default="base", nullable=False)
    dimensions: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    new_users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engaged_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engagement_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    average_session_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bounce_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    screen_page_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class GA4LandingPagesDaily(Base):
    __tablename__ = "ga4_landing_pages_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "landing_page", name="uq_ga4_lp_daily"),
        Index("ix_ga4_lp_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    landing_page: Mapped[str] = mapped_column(String(700), nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bounce_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GA4LandingPageDeviceDaily(Base):
    """Per-page × deviceCategory daily rollup. Powers the device filter on
    the Pages dashboard (e.g. "show me how this page performs on mobile vs
    desktop"). GA4-only — no GSC join at this dimensionality."""

    __tablename__ = "ga4_landing_page_device_daily"
    __table_args__ = (
        UniqueConstraint(
            "property_id", "date", "landing_page", "device_category",
            name="uq_ga4_lp_device_daily",
        ),
        Index("ix_ga4_lp_device_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    landing_page: Mapped[str] = mapped_column(String(500), nullable=False)
    device_category: Mapped[str] = mapped_column(String(100), nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engaged_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    bounce_rate: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    avg_session_duration: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
    exits: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GA4TrafficSourcesDaily(Base):
    __tablename__ = "ga4_traffic_sources_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "source", "medium", "campaign", name="uq_ga4_ts_daily"),
        Index("ix_ga4_ts_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    source: Mapped[str] = mapped_column(String(250), nullable=False)
    medium: Mapped[str] = mapped_column(String(250), nullable=False)
    campaign: Mapped[str] = mapped_column(String(250), nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GA4DevicesDaily(Base):
    __tablename__ = "ga4_devices_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "device_category", name="uq_ga4_dev_daily"),
        Index("ix_ga4_dev_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    device_category: Mapped[str] = mapped_column(String(100), nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GA4GeoDaily(Base):
    __tablename__ = "ga4_geo_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "country", "region", name="uq_ga4_geo_daily"),
        Index("ix_ga4_geo_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    country: Mapped[str] = mapped_column(String(100), nullable=False)
    region: Mapped[str] = mapped_column(String(200), nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GA4EventsDaily(Base):
    __tablename__ = "ga4_events_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "event_name", name="uq_ga4_ev_daily"),
        Index("ix_ga4_ev_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    event_name: Mapped[str] = mapped_column(String(500), nullable=False)

    event_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GA4ChannelsDaily(Base):
    """Per-day rollup by sessionDefaultChannelGroup (Organic Search, Direct, Paid, etc.)."""

    __tablename__ = "ga4_channels_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "channel_group", name="uq_ga4_channels_daily"),
        Index("ix_ga4_channels_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    channel_group: Mapped[str] = mapped_column(String(100), nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    conversions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    total_revenue: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)


class GA4HourlyMetrics(Base):
    """Hour-of-day traffic patterns (0-23 per date)."""

    __tablename__ = "ga4_hourly_metrics"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "hour", name="uq_ga4_hourly_metrics"),
        Index("ix_ga4_hourly_metrics_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    screen_page_views: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class GA4UserTypeDaily(Base):
    """New vs returning user split per day."""

    __tablename__ = "ga4_user_type_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "user_type", name="uq_ga4_user_type_daily"),
        Index("ix_ga4_user_type_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    user_type: Mapped[str] = mapped_column(String(50), nullable=False)

    sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    users: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    engaged_sessions: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
