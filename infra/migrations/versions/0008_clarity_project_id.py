"""Add clarity_project_id column to properties

Revision ID: 0008
Revises: 0007
Create Date: 2026-05-13

Phase D1 of the insights roadmap — lets each property store its Microsoft
Clarity project ID so the UI can deep-link to heatmaps / recordings.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision: str = "0008"
down_revision: str | None = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "properties",
        sa.Column("clarity_project_id", sa.String(50), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("properties", "clarity_project_id")
