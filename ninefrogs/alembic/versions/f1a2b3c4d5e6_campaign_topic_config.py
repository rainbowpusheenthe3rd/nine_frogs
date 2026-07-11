"""Replace level_min/level_max with topic_config JSONB on campaigns

Revision ID: f1a2b3c4d5e6
Revises: e1f2a3b4c5d6
Create Date: 2026-05-26
"""
from __future__ import annotations

from alembic import op

revision = "f1a2b3c4d5e6"
down_revision = "e1f2a3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS level_min")
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS level_max")
    op.execute(
        "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS "
        "topic_config JSONB NOT NULL DEFAULT '{}'"
    )


def downgrade() -> None:
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS topic_config")
    op.execute(
        "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS level_min INTEGER NOT NULL DEFAULT 1"
    )
    op.execute(
        "ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS level_max INTEGER NOT NULL DEFAULT 9"
    )
