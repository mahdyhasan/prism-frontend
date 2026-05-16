from __future__ import annotations

from sqlalchemy import String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prism.db.base import Base


class Tenant(Base):
    __tablename__ = "tenants"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    plan: Mapped[str] = mapped_column(String(50), default="free", nullable=False)

    users: Mapped[list["User"]] = relationship(back_populates="tenant")  # type: ignore[name-defined]  # noqa: F821
    properties: Mapped[list["Property"]] = relationship(back_populates="tenant")  # type: ignore[name-defined]  # noqa: F821
