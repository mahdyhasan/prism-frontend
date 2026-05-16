from __future__ import annotations

from sqlalchemy import JSON, BigInteger, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prism.db.base import Base


class Property(Base):
    __tablename__ = "properties"

    tenant_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("tenants.id"), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    ga4_property_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    gsc_site_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    timezone: Mapped[str] = mapped_column(String(100), default="UTC", nullable=False)
    currency: Mapped[str] = mapped_column(String(10), default="USD", nullable=False)
    status: Mapped[str] = mapped_column(String(50), default="pending", nullable=False)
    linked_by_user_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=True)

    # GA4 event names this property considers "primary" conversions.
    # Used for conversion-rate KPIs. Null = no events configured yet.
    primary_conversion_events: Mapped[list[str] | None] = mapped_column(JSON, nullable=True)

    # Microsoft Clarity project ID (10-char alphanumeric, set by the user in
    # Settings). When non-null, the UI shows deep-link buttons to Clarity.
    clarity_project_id: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # AES-256-GCM encrypted Clarity Data Export API token.  When present,
    # the nightly worker pulls per-URL frustration metrics and stores them in
    # clarity_page_daily. Null = D1 deep-link only, no data pull.
    clarity_api_token_encrypted: Mapped[str | None] = mapped_column(Text(), nullable=True)

    tenant: Mapped["Tenant"] = relationship(back_populates="properties")  # type: ignore[name-defined]  # noqa: F821
    members: Mapped[list["PropertyMember"]] = relationship(back_populates="property")  # type: ignore[name-defined]  # noqa: F821
    sync_jobs: Mapped[list["SyncJob"]] = relationship(back_populates="property")  # type: ignore[name-defined]  # noqa: F821
    llm_config: Mapped["PropertyLLMConfig | None"] = relationship(back_populates="property", uselist=False)  # type: ignore[name-defined]  # noqa: F821


class PropertyMember(Base):
    __tablename__ = "property_members"
    __table_args__ = (UniqueConstraint("property_id", "user_id", name="uq_property_user"),)

    property_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("properties.id"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.id"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(50), default="owner", nullable=False)

    property: Mapped["Property"] = relationship(back_populates="members")
    user: Mapped["User"] = relationship(back_populates="property_memberships")  # type: ignore[name-defined]  # noqa: F821
