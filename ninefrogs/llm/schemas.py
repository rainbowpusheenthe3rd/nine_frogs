"""Pydantic models for all structured LLM outputs."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ResearchQueries(BaseModel):
    queries: list[str] = Field(..., description="Search queries to gather information")


class SyllabusSection(BaseModel):
    title: str
    summary: str
    learning_objectives: list[str] = Field(..., min_length=2, max_length=6)
    key_concepts: list[str] = Field(..., min_length=2, max_length=12)


class Syllabus(BaseModel):
    title: str
    overview: str
    sections: list[SyllabusSection] = Field(..., min_length=3, max_length=8)


class QuestionSet(BaseModel):
    questions: list[str] = Field(..., min_length=3, max_length=10)


class FlashcardItem(BaseModel):
    front: str
    back: str
    hint: str | None = None
    tags: list[str] = Field(default_factory=list)


class FlashcardBatch(BaseModel):
    cards: list[FlashcardItem]


# ── Repo → drills-style syllabus (with fundamentals cross-links) ───────────────

class Prerequisite(BaseModel):
    """A cross-link to a science-fundamentals syllabus this material rests on.

    ``subject`` is the slug of another drills syllabus (e.g. "linear_algebra").
    ``status`` is filled in *after* generation by resolving the slug against the
    syllabuses that actually exist — the LLM should leave it unset.
    """
    subject: str = Field(..., description="Slug of a fundamentals syllabus, e.g. linear_algebra")
    levels: list[int] = Field(default_factory=list, description="Relevant level numbers in that subject")
    why: str = Field(..., description="One line: why this fundamental is needed here")
    status: Literal["linked", "proposed"] | None = None


class RepoSyllabusLevel(BaseModel):
    level: int = Field(..., ge=1, le=9)
    title: str
    mode: Literal["cards", "mixed", "exercises"] = "mixed"
    description: str
    concepts: list[str] = Field(..., min_length=2, max_length=12)
    objectives: list[str] = Field(..., min_length=2, max_length=6)
    prerequisites: list[Prerequisite] = Field(default_factory=list)
    flashcard_count: int = 14
    exercise_count: int = 0


class RepoSyllabus(BaseModel):
    """A drills-style syllabus generated from a code repository.

    Serialises straight to a ``drills/syllabuses/<subject>.yaml`` that the
    existing loader (``lab.subjects.load_all_syllabuses``) and drills→cards
    bridge (``web.routes.drills``) already consume.
    """
    subject: str = Field(..., description="Short slug, e.g. 'biopoly'")
    title: str
    domain: str = Field("ml", description="Grouping domain, e.g. ml / mathematics / cs_foundations")
    type: Literal["theory_heavy", "applied", "mixed"] = "applied"
    description: str
    sources: list[str] = Field(default_factory=list)
    prerequisites: list[Prerequisite] = Field(
        default_factory=list, description="Subject-wide fundamentals this course rests on"
    )
    levels: list[RepoSyllabusLevel] = Field(..., min_length=3, max_length=9)
