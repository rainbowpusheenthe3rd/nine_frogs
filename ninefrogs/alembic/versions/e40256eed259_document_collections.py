"""document collections

Revision ID: e40256eed259
Revises: f77bd058b658
Create Date: 2026-03-21

Adds document_collections, documents, document_chunks tables and
pins research_sessions to an optional collection via collection_id.
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "e40256eed259"
down_revision = "f77bd058b658"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tables may already exist if created by create_all() before migrations were introduced.
    op.execute("""
        CREATE TABLE IF NOT EXISTS document_collections (
            id UUID NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id),
            UNIQUE (name)
        )
    """)

    op.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id UUID NOT NULL,
            collection_id UUID NOT NULL REFERENCES document_collections(id) ON DELETE CASCADE,
            title TEXT NOT NULL,
            source_type VARCHAR(50) NOT NULL,
            source_uri TEXT,
            content_sha VARCHAR(64) NOT NULL,
            added_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_documents_content_sha ON documents(content_sha)")

    op.execute("""
        CREATE TABLE IF NOT EXISTS document_chunks (
            id UUID NOT NULL,
            document_id UUID NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            collection_id UUID NOT NULL REFERENCES document_collections(id) ON DELETE CASCADE,
            content TEXT NOT NULL,
            position INTEGER NOT NULL,
            content_sha VARCHAR(64) NOT NULL,
            embedding vector(768),
            added_at TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL,
            PRIMARY KEY (id)
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_collection_id ON document_chunks(collection_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_document_chunks_content_sha ON document_chunks(content_sha)")

    # Pin research sessions to an optional collection
    op.execute("""
        ALTER TABLE research_sessions
        ADD COLUMN IF NOT EXISTS collection_id UUID
        REFERENCES document_collections(id) ON DELETE SET NULL
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_research_sessions_collection_id ON research_sessions(collection_id)")


def downgrade() -> None:
    op.drop_index("ix_research_sessions_collection_id", table_name="research_sessions")
    op.drop_constraint("fk_research_sessions_collection_id", "research_sessions", type_="foreignkey")
    op.drop_column("research_sessions", "collection_id")

    op.drop_index("ix_document_chunks_content_sha", table_name="document_chunks")
    op.drop_index("ix_document_chunks_collection_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_index("ix_documents_content_sha", table_name="documents")
    op.drop_table("documents")

    op.drop_table("document_collections")
