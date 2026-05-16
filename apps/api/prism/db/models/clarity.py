from __future__ import annotations

from datetime import date

from sqlalchemy import BigInteger, Date, Float, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from prism.db.base import Base


class ClarityPageDaily(Base):
    """Per-URL daily frustration signals pulled from the Microsoft Clarity
    Data Export API.

    Metrics:
    - session_count    Total sessions that visited this URL
    - dead_clicks      Clicks that triggered no response
    - rage_clicks      Rapid repeated clicks (user frustration signal)
    - quick_backs      Sessions that immediately returned to the SERP
    - scroll_depth_avg Average scroll depth (0.0–1.0)

    frustration_score is NOT stored — compute at query time:
        (dead_clicks + 2 * rage_clicks + quick_backs) / session_count
    """

    __tablename__ = "clarity_page_daily"
    __table_args__ = (
        UniqueConstraint("property_id", "date", "page_url", name="uq_clarity_page_daily"),
        Index("ix_clarity_page_daily_property_date", "property_id", "date"),
    )

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    page_url: Mapped[str] = mapped_column(String(500), nullable=False)

    session_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    dead_clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    rage_clicks: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    quick_backs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    scroll_depth_avg: Mapped[float] = mapped_column(Float, default=0.0, nullable=False)
