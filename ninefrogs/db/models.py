from __future__ import annotations

import uuid
from datetime import date, datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import BigInteger, Boolean, Date, Float, ForeignKey, Integer, JSON, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from db.engine import Base


# ── Document collections ───────────────────────────────────────────────────────

class DocumentCollection(Base):
    __tablename__ = "document_collections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    documents: Mapped[list[Document]] = relationship(
        "Document", back_populates="collection", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk", back_populates="collection", cascade="all, delete-orphan"
    )


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_collections.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(Text, nullable=False)
    # Source type: "upload" | "crawl" | "paste" | "api" | "pdf" — open string
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    # URL, filepath, or None for paste/manual
    source_uri: Mapped[str | None] = mapped_column(Text, nullable=True)
    # SHA-256 of the full raw content — used to skip re-ingesting identical files
    content_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    added_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    collection: Mapped[DocumentCollection] = relationship(
        "DocumentCollection", back_populates="documents"
    )
    chunks: Mapped[list[DocumentChunk]] = relationship(
        "DocumentChunk", back_populates="document", cascade="all, delete-orphan"
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Denormalised for efficient collection-scoped vector search
    collection_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_collections.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # SHA-256 of this chunk's content
    content_sha: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    embedding: Mapped[list | None] = mapped_column(Vector(768), nullable=True)
    added_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    document: Mapped[Document] = relationship("Document", back_populates="chunks")
    collection: Mapped[DocumentCollection] = relationship(
        "DocumentCollection", back_populates="chunks"
    )


# ── Research sessions ──────────────────────────────────────────────────────────

class ResearchSession(Base):
    __tablename__ = "research_sessions"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    # Optional: pin this session to a document collection for retrieval
    collection_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("document_collections.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    # pending | running | done | generating_cards | error
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    sections: Mapped[list[SyllabusSection]] = relationship(
        "SyllabusSection", back_populates="session", cascade="all, delete-orphan"
    )
    flashcards: Mapped[list[Flashcard]] = relationship(
        "Flashcard", back_populates="session", cascade="all, delete-orphan"
    )
    chunks: Mapped[list[KnowledgeChunk]] = relationship(
        "KnowledgeChunk", back_populates="session", cascade="all, delete-orphan"
    )


class SyllabusSection(Base):
    __tablename__ = "syllabus_sections"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # Drill syllabus level (1-9), null for free-topic research sessions
    drill_level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    learning_objectives: Mapped[list] = mapped_column(JSON, default=list)
    key_concepts: Mapped[list] = mapped_column(JSON, default=list)
    # pending | accepted | rejected
    status: Mapped[str] = mapped_column(String(50), default="pending")
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    session: Mapped[ResearchSession] = relationship("ResearchSession", back_populates="sections")
    flashcards: Mapped[list[Flashcard]] = relationship(
        "Flashcard", back_populates="section", cascade="all, delete-orphan"
    )


class Flashcard(Base):
    __tablename__ = "flashcards"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    section_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("syllabus_sections.id", ondelete="CASCADE"),
        nullable=False,
    )
    front: Mapped[str] = mapped_column(Text, nullable=False)
    back: Mapped[str] = mapped_column(Text, nullable=False)
    hint: Mapped[str | None] = mapped_column(Text, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # pending | approved | rejected
    status: Mapped[str] = mapped_column(String(50), default="pending")
    anki_note_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    session: Mapped[ResearchSession] = relationship("ResearchSession", back_populates="flashcards")
    section: Mapped[SyllabusSection] = relationship("SyllabusSection", back_populates="flashcards")


class KnowledgeChunk(Base):
    __tablename__ = "knowledge_chunks"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("research_sessions.id", ondelete="CASCADE"),
        nullable=False,
    )
    # wikipedia | web
    source_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source_title: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # 768-dim BGE embedding; nullable until embedded
    embedding: Mapped[list | None] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    session: Mapped[ResearchSession] = relationship("ResearchSession", back_populates="chunks")


# ── Nine Frog Labs ─────────────────────────────────────────────────────────────

class CodingChallenge(Base):
    __tablename__ = "coding_challenges"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    slug: Mapped[str] = mapped_column(String(120), unique=True, nullable=False, index=True)
    # "drills_yaml" | "leetcode" | "mbpp" | "humaneval" | "neetcode"
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="drills_yaml")
    subject: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    # Neetcode / algorithm pattern slug e.g. "sliding_window", "dp_1d" — null for non-algo challenges
    pattern: Mapped[str | None] = mapped_column(String(80), nullable=True, index=True)
    level: Mapped[int | None] = mapped_column(Integer, nullable=True)
    difficulty: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    # "module" | "function" | "debug" | "cli_script" | "docker_service" | "docker_app" | "rust"
    type: Mapped[str] = mapped_column(String(50), nullable=False, default="module")
    title: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    starter_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    hints: Mapped[list] = mapped_column(JSON, default=list)
    test_code: Mapped[str] = mapped_column(Text, nullable=False)
    solution_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    docker_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    tags: Mapped[list] = mapped_column(JSON, default=list)
    # 768-dim code embedding (jina-embeddings-v2-base-code); nullable until populated
    embedding: Mapped[list | None] = mapped_column(Vector(768), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )

    progress: Mapped[ChallengeProgress | None] = relationship(
        "ChallengeProgress", back_populates="challenge", uselist=False,
        cascade="all, delete-orphan"
    )
    attempts: Mapped[list[CodingAttempt]] = relationship(
        "CodingAttempt", back_populates="challenge", cascade="all, delete-orphan"
    )
    campaign_entries: Mapped[list[CampaignEntry]] = relationship(
        "CampaignEntry", back_populates="challenge", cascade="all, delete-orphan"
    )


class ChallengeProgress(Base):
    """SM-2 state per challenge — global across campaign and review modes."""
    __tablename__ = "challenge_progress"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coding_challenges.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    sm2_ef: Mapped[float] = mapped_column(Float, nullable=False, default=2.5)
    sm2_interval: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    sm2_repetitions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    next_review: Mapped[date | None] = mapped_column(Date, nullable=True)
    total_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_passes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_attempted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    challenge: Mapped[CodingChallenge] = relationship(
        "CodingChallenge", back_populates="progress"
    )


class CodingAttempt(Base):
    """One row per submission (pass, fail, or give-up)."""
    __tablename__ = "coding_attempts"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coding_challenges.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    submitted_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "in_progress" | "passed" | "failed" | "gave_up"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="in_progress")
    hints_used: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    code_submitted: Mapped[str | None] = mapped_column(Text, nullable=True)
    test_output: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_practice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    challenge: Mapped[CodingChallenge] = relationship(
        "CodingChallenge", back_populates="attempts"
    )
    campaign: Mapped[Campaign | None] = relationship(
        "Campaign", back_populates="attempts"
    )
    campaign_entry: Mapped[CampaignEntry | None] = relationship(
        "CampaignEntry", back_populates="attempt", foreign_keys="CampaignEntry.attempt_id"
    )


class Campaign(Base):
    """A timed, multi-session run through selected syllabus topics."""
    __tablename__ = "campaigns"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    # Denormalised display list — unique subject slugs derived from topic_config at creation
    subjects: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    # {"selections": [{"subject": "dsa", "topic": "trees"}, ...], "neetcode_difficulty": [1, 2]}
    topic_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now()
    )
    last_active_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), server_default=func.now(), onupdate=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    # "active" | "completed" | "abandoned"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="active")
    total_time_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_practice: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    entries: Mapped[list[CampaignEntry]] = relationship(
        "CampaignEntry", back_populates="campaign",
        cascade="all, delete-orphan", order_by="CampaignEntry.position"
    )
    attempts: Mapped[list[CodingAttempt]] = relationship(
        "CodingAttempt", back_populates="campaign"
    )


class CampaignEntry(Base):
    """One challenge slot within a campaign, in syllabus order."""
    __tablename__ = "campaign_entries"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    campaign_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("campaigns.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    challenge_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coding_challenges.id", ondelete="CASCADE"),
        nullable=False,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    # "pending" | "passed" | "failed" | "gave_up"
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="pending")
    attempt_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("coding_attempts.id", ondelete="SET NULL"),
        nullable=True,
    )
    time_spent_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    campaign: Mapped[Campaign] = relationship("Campaign", back_populates="entries")
    challenge: Mapped[CodingChallenge] = relationship(
        "CodingChallenge", back_populates="campaign_entries"
    )
    attempt: Mapped[CodingAttempt | None] = relationship(
        "CodingAttempt", back_populates="campaign_entry",
        foreign_keys=[attempt_id]
    )
