"""Nine Frog Labs — coding challenge tables

Revision ID: b1c2d3e4f5a6
Revises: a1b2c3d4e5f6
Create Date: 2026-05-24

Adds five tables for the Nine Frog Labs coding challenge module:
  coding_challenges, challenge_progress, campaigns, campaign_entries,
  coding_attempts (in that order to satisfy FK dependencies).
"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "b1c2d3e4f5a6"
down_revision = "a1b2c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        CREATE TABLE IF NOT EXISTS coding_challenges (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug        VARCHAR(120) NOT NULL UNIQUE,
            source      VARCHAR(50)  NOT NULL DEFAULT 'drills_yaml',
            subject     VARCHAR(80)  NOT NULL,
            pattern     VARCHAR(80),
            level       INTEGER,
            difficulty  INTEGER      NOT NULL DEFAULT 1,
            type        VARCHAR(50)  NOT NULL DEFAULT 'module',
            title       TEXT         NOT NULL,
            prompt      TEXT         NOT NULL,
            starter_code TEXT,
            hints       JSONB        NOT NULL DEFAULT '[]',
            test_code   TEXT         NOT NULL,
            solution_code TEXT,
            docker_config JSONB,
            tags        JSONB        NOT NULL DEFAULT '[]',
            embedding   VECTOR(768),
            created_at  TIMESTAMPTZ  NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_coding_challenges_subject ON coding_challenges (subject)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_coding_challenges_slug    ON coding_challenges (slug)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_coding_challenges_pattern ON coding_challenges (pattern)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS challenge_progress (
            id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            challenge_id     UUID NOT NULL UNIQUE REFERENCES coding_challenges(id) ON DELETE CASCADE,
            sm2_ef           REAL NOT NULL DEFAULT 2.5,
            sm2_interval     INTEGER NOT NULL DEFAULT 1,
            sm2_repetitions  INTEGER NOT NULL DEFAULT 0,
            next_review      DATE,
            total_attempts   INTEGER NOT NULL DEFAULT 0,
            total_passes     INTEGER NOT NULL DEFAULT 0,
            last_attempted_at TIMESTAMPTZ
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_challenge_progress_challenge_id ON challenge_progress (challenge_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_challenge_progress_next_review  ON challenge_progress (next_review)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS campaigns (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name                TEXT NOT NULL,
            subjects            JSONB NOT NULL DEFAULT '[]',
            level_min           INTEGER NOT NULL,
            level_max           INTEGER NOT NULL,
            started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            last_active_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            completed_at        TIMESTAMPTZ,
            status              VARCHAR(20) NOT NULL DEFAULT 'active',
            total_time_seconds  INTEGER NOT NULL DEFAULT 0,
            is_practice         BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS coding_attempts (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            challenge_id        UUID NOT NULL REFERENCES coding_challenges(id) ON DELETE CASCADE,
            campaign_id         UUID REFERENCES campaigns(id) ON DELETE SET NULL,
            started_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            submitted_at        TIMESTAMPTZ,
            time_spent_seconds  INTEGER,
            status              VARCHAR(20) NOT NULL DEFAULT 'in_progress',
            hints_used          INTEGER NOT NULL DEFAULT 0,
            code_submitted      TEXT,
            test_output         TEXT,
            is_practice         BOOLEAN NOT NULL DEFAULT FALSE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_coding_attempts_challenge_id ON coding_attempts (challenge_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_coding_attempts_campaign_id  ON coding_attempts (campaign_id)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS campaign_entries (
            id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            campaign_id         UUID NOT NULL REFERENCES campaigns(id) ON DELETE CASCADE,
            challenge_id        UUID NOT NULL REFERENCES coding_challenges(id) ON DELETE CASCADE,
            position            INTEGER NOT NULL,
            status              VARCHAR(20) NOT NULL DEFAULT 'pending',
            attempt_id          UUID REFERENCES coding_attempts(id) ON DELETE SET NULL,
            time_spent_seconds  INTEGER
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_campaign_entries_campaign_id ON campaign_entries (campaign_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS campaign_entries")
    op.execute("DROP TABLE IF EXISTS coding_attempts")
    op.execute("DROP TABLE IF EXISTS campaigns")
    op.execute("DROP TABLE IF EXISTS challenge_progress")
    op.execute("DROP TABLE IF EXISTS coding_challenges")
