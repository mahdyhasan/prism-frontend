from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prism.db.base import Base


class SyncJob(Base):
    __tablename__ = "sync_jobs"

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False, index=True)
    source: Mapped[str] = mapped_column(String(10), nullable=False)  # ga4 | gsc
    kind: Mapped[str] = mapped_column(String(50), nullable=False)    # daily | backfill | manual
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)  # pending | running | done | failed
    rows_pulled: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    property: Mapped["Property"] = relationship(back_populates="sync_jobs")  # type: ignore[name-defined]  # noqa: F821


class AuditLog(Base):
    __tablename__ = "audit_log"

    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False, index=True)
    user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)
    action: Mapped[str] = mapped_column(String(200), nullable=False)
    target_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    target_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)
