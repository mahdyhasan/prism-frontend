"""Add primary_conversion_events JSON column to properties

Revision ID: 0007
Revises: 0006
Create Date: 2026-05-13

Phase A of the insights roadmap — lets users designate which GA4 event
names count as primary conversions for conversion-rate calculations.
A nullable JSON column means existing rows need no backfill.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0007"
down_revision: str | None = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("primary_conversion_events", sa.JSON(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("properties", "primary_conversion_events")
