"""Flashcard generation pipeline.

For each accepted syllabus section:
  1. LLM generates 6-8 targeted questions.
  2. Cross-direction retrieval (forward + backward query angles).
  3. LLM generates 1-2 Anki cards per question.
  4. Cards saved to DB with status='pending' for human review.
"""
from __future__ import annotations

import asyncio
from loguru import logger
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.engine import async_session_factory
from db.models import Flashcard, SyllabusSection
from knowledge.retriever import cross_direction_search
from llm.client import get_llm_client
from llm.schemas import FlashcardBatch, QuestionSet
from research.prompts import (
    FLASHCARD_SYSTEM,
    SECTION_QUERY_SYSTEM,
    flashcard_user,
    section_query_user,
)



# ── entry points ──────────────────────────────────────────────────────────────

async def generate_for_session(session_id: uuid.UUID) -> None:
    """Generate flashcards for all accepted sections. Background task."""
    async with async_session_factory() as db:
        result = await db.execute(
            select(SyllabusSection)
            .where(SyllabusSection.session_id == session_id)
            .where(SyllabusSection.status == "accepted")
            .order_by(SyllabusSection.position)
        )
        sections = result.scalars().all()

        if not sections:
            logger.warning("No accepted sections for session %s", session_id)
            return

        for section in sections:
            await _generate_for_section(section, db)

        logger.info(
            "Card generation complete for session %s (%d sections)",
            session_id,
            len(sections),
        )


# ── per-section generation ────────────────────────────────────────────────────

async def _generate_for_section(section: SyllabusSection, db: AsyncSession) -> None:
    llm = get_llm_client()
    session_id = section.session_id

    # Step 1: generate questions for this section
    try:
        q_result = await llm.complete_json(
            messages=[
                {"role": "system", "content": SECTION_QUERY_SYSTEM},
                {
                    "role": "user",
                    "content": section_query_user(
                        section.title,
                        section.summary,
                        section.learning_objectives,
                        section.key_concepts,
                    ),
                },
            ],
            schema=QuestionSet,
            temperature=0.4,
        )
    except Exception as exc:
        logger.warning("Question generation failed for section %s: %s", section.id, exc)
        return

    for question in q_result.questions:
        # Step 2: cross-direction retrieval
        chunks = await cross_direction_search(
            question=question,
            section_title=section.title,
            session_id=session_id,
            db=db,
            top_k=6,
        )
        context_texts = [c.text for c in chunks[:4]]

        # Step 3: generate flashcards
        try:
            card_result = await llm.complete_json(
                messages=[
                    {"role": "system", "content": FLASHCARD_SYSTEM},
                    {
                        "role": "user",
                        "content": flashcard_user(section.title, question, context_texts),
                    },
                ],
                schema=FlashcardBatch,
                temperature=0.3,
            )

            for card in card_result.cards:
                db.add(
                    Flashcard(
                        session_id=session_id,
                        section_id=section.id,
                        front=card.front,
                        back=card.back,
                        hint=card.hint,
                        tags=card.tags,
                        status="pending",
                    )
                )

        except Exception as exc:
            logger.warning(
                "Card generation failed for question %r in section %s: %s",
                question,
                section.id,
                exc,
            )

        await asyncio.sleep(0)  # yield to event loop between questions

    await db.commit()
    logger.info("Generated cards for section: %s", section.title)
