"""add drill_level to syllabus_sections

Revision ID: a1b2c3d4e5f6
Revises: e40256eed259
Create Date: 2026-04-09

Adds drill_level (nullable integer) to syllabus_sections so flashcards
generated from drill syllabuses carry their level context through to
the prompt calibration system.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "e40256eed259"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE syllabus_sections
        ADD COLUMN IF NOT EXISTS drill_level INTEGER
    """)


def downgrade() -> None:
    op.drop_column("syllabus_sections", "drill_level")
