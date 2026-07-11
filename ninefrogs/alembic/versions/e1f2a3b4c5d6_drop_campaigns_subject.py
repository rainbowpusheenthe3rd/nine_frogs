"""Drop legacy campaigns.subject column (replaced by campaigns.subjects JSONB)

Revision ID: e1f2a3b4c5d6
Revises: d1e2f3a4b5c6
Create Date: 2026-05-25
"""
from __future__ import annotations

from alembic import op

revision = "e1f2a3b4c5d6"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS subject")


def downgrade() -> None:
    op.execute("ALTER TABLE campaigns ADD COLUMN IF NOT EXISTS subject VARCHAR(80) NOT NULL DEFAULT ''")
