from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prism.db.base import Base


class User(Base):
    __tablename__ = "users"

    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="owner", nullable=False)
    google_sub: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    google_refresh_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
    password_hash: Mapped[str | None] = mapped_column(String(255), nullable=True)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="users")  # type: ignore[name-defined]  # noqa: F821
    property_memberships: Mapped[list["PropertyMember"]] = relationship(back_populates="user")  # type: ignore[name-defined]  # noqa: F821
