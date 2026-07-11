"""Practice mode — is_practice flag on coding_attempts and campaigns

Revision ID: c1d2e3f4a5b6
Revises: b1c2d3e4f5a6
Create Date: 2026-05-24

Adds is_practice boolean to coding_attempts and campaigns so practice
sessions are excluded from SM-2 updates and report card stats.
"""
from __future__ import annotations

from alembic import op

revision = "c1d2e3f4a5b6"
down_revision = "b1c2d3e4f5a6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE coding_attempts
        ADD COLUMN IF NOT EXISTS is_practice BOOLEAN NOT NULL DEFAULT FALSE
    """)
    op.execute("""
        ALTER TABLE campaigns
        ADD COLUMN IF NOT EXISTS is_practice BOOLEAN NOT NULL DEFAULT FALSE
    """)


def downgrade() -> None:
    op.execute("ALTER TABLE coding_attempts DROP COLUMN IF EXISTS is_practice")
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS is_practice")
