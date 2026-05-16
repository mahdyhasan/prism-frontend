from __future__ import annotations

from datetime import date, datetime

import sqlalchemy as sa
from sqlalchemy import (
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from prism.db.base import Base


class DailyBrief(Base):
    """AI-generated daily narrative brief for a property."""

    __tablename__ = "daily_briefs"
    __table_args__ = (
        UniqueConstraint("property_id", "brief_date", name="uq_daily_briefs_property_date"),
        {"mysql_engine": "InnoDB", "mysql_charset": "utf8mb4", "mysql_collate": "utf8mb4_0900_ai_ci"},
    )

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    brief_date: Mapped[date] = mapped_column(Date, nullable=False)
    brief_json: Mapped[str | None] = mapped_column(Text(length=2**32 - 1), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=sa.text("NOW()"), nullable=False,
    )
    generation_count: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False,
    )
