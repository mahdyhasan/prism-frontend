from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from prism.db.base import Base


class PropertyLLMConfig(Base):
    __tablename__ = "property_llm_configs"

    property_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("properties.id", ondelete="CASCADE"), nullable=False, index=True
    )
    llm_provider: Mapped[str] = mapped_column(String(50), nullable=False, default="anthropic")
    llm_model: Mapped[str] = mapped_column(String(100), nullable=False, default="claude-sonnet-4-6")
    llm_api_key_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)

    property: Mapped["Property"] = relationship(back_populates="llm_config")  # type: ignore[name-defined]  # noqa: F821
