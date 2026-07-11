"""Neetcode support — multi-subject campaigns + pattern field on challenges

Revision ID: d1e2f3a4b5c6
Revises: c1d2e3f4a5b6
Create Date: 2026-05-25

- campaigns.subjects  JSONB (replaces single campaigns.subject VARCHAR)
- coding_challenges.pattern  VARCHAR(80) for algorithm pattern grouping
"""
from __future__ import annotations

from alembic import op

revision = "d1e2f3a4b5c6"
down_revision = "c1d2e3f4a5b6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add multi-subject list to campaigns, seeding from the old single subject
    op.execute("""
        ALTER TABLE campaigns
        ADD COLUMN IF NOT EXISTS subjects JSONB NOT NULL DEFAULT '[]'
    """)
    op.execute("""
        UPDATE campaigns
        SET subjects = jsonb_build_array(subject)
        WHERE jsonb_array_length(subjects) = 0
          AND subject IS NOT NULL
          AND subject <> ''
    """)

    # Algorithm pattern slug on coding_challenges
    op.execute("""
        ALTER TABLE coding_challenges
        ADD COLUMN IF NOT EXISTS pattern VARCHAR(80)
    """)
    op.execute("""
        CREATE INDEX IF NOT EXISTS ix_coding_challenges_pattern
        ON coding_challenges (pattern)
    """)


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_coding_challenges_pattern")
    op.execute("ALTER TABLE coding_challenges DROP COLUMN IF EXISTS pattern")
    op.execute("ALTER TABLE campaigns DROP COLUMN IF EXISTS subjects")
