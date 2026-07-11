"""Add notes column to challenge_progress

Revision ID: g1h2i3j4k5l6
Revises: f1a2b3c4d5e6
Create Date: 2026-05-26
"""
from __future__ import annotations

from alembic import op

revision = "g1h2i3j4k5l6"
down_revision = "f1a2b3c4d5e6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE challenge_progress ADD COLUMN IF NOT EXISTS notes TEXT"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE challenge_progress DROP COLUMN IF EXISTS notes"
    )
