"""Pydantic models for all structured LLM outputs."""
from __future__ import annotations

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
