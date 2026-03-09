"""Deep research pipeline.

Runs as a background asyncio task.  Progress is streamed to the browser via
Server-Sent Events through the EventStore.

Algorithm:
  1. Iterative query generation  (2 rounds × 5 queries = up to 10 queries)
  2. Hybrid retrieval per query  (BM25 Wikipedia + pgvector)
  3. Syllabus synthesis          (LLM with top-25 RRF-ranked chunks as context)
  4. Persist chunks (with embeddings) + syllabus sections to PostgreSQL
"""
from __future__ import annotations

import asyncio
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.engine import async_session_factory
from db.models import KnowledgeChunk, ResearchSession, SyllabusSection
from embeddings import embed
from knowledge.retriever import RetrievedChunk, hybrid_search
from knowledge.wikipedia import wiki_ready
from llm.client import get_llm_client
from llm.schemas import ResearchQueries, Syllabus
from research.events import ResearchEvent, event_store
from research.prompts import (
    QUERY_GEN_SYSTEM,
    SYLLABUS_SYSTEM,
    query_gen_user,
    syllabus_user,
)

logger = logging.getLogger(__name__)

_MAX_CONTEXT_CHARS = 10_000
_RESEARCH_ITERATIONS = 2
_QUERIES_PER_ITER = 5
_TOP_CHUNKS = 25


# ── helpers ───────────────────────────────────────────────────────────────────

async def _emit(session_id: uuid.UUID, type_: str, **payload: object) -> None:
    await event_store.publish(session_id, ResearchEvent(type=type_, payload=dict(payload)))


def _dedup(chunks: list[RetrievedChunk]) -> list[RetrievedChunk]:
    seen: set[str] = set()
    out: list[RetrievedChunk] = []
    for c in chunks:
        if c.key not in seen:
            seen.add(c.key)
            out.append(c)
    return out


def _format_context(chunks: list[RetrievedChunk], max_chars: int = _MAX_CONTEXT_CHARS) -> str:
    parts: list[str] = []
    total = 0
    for c in chunks:
        label = f"[{c.source_type.upper()}] {c.title or 'Source'}"
        entry = f"{label}\n{c.text[:800]}"
        if total + len(entry) > max_chars:
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n---\n\n".join(parts)


# ── entry point ───────────────────────────────────────────────────────────────

async def run_research(session_id: uuid.UUID) -> None:
    """Background task: run full research pipeline for a session."""
    async with async_session_factory() as db:
        session = await db.get(ResearchSession, session_id)
        if not session:
            return
        topic = session.topic
        try:
            await _pipeline(session_id, topic, db)
        except Exception as exc:
            logger.exception("Research pipeline error for session %s: %s", session_id, exc)
            await _emit(session_id, "error", message=str(exc))
            session = await db.get(ResearchSession, session_id)
            if session:
                session.status = "error"
                await db.commit()


# ── pipeline ──────────────────────────────────────────────────────────────────

async def _pipeline(session_id: uuid.UUID, topic: str, db: AsyncSession) -> None:
    llm = get_llm_client()

    # Wait for Wikipedia index (with generous timeout)
    await _emit(session_id, "status", message="Waiting for knowledge base…")
    try:
        await asyncio.wait_for(wiki_ready.wait(), timeout=360.0)
    except asyncio.TimeoutError:
        await _emit(session_id, "status", message="Wikipedia index not ready — using web only")

    # ── Phase 1: iterative query generation + retrieval ───────────────────────
    await _emit(session_id, "status", message="Planning research approach…")

    all_chunks: list[RetrievedChunk] = []
    all_queries: list[str] = []

    for iteration in range(_RESEARCH_ITERATIONS):
        try:
            result = await llm.complete_json(
                messages=[
                    {"role": "system", "content": QUERY_GEN_SYSTEM},
                    {"role": "user", "content": query_gen_user(topic, all_queries, iteration)},
                ],
                schema=ResearchQueries,
                temperature=0.7,
            )
            new_queries = result.queries[:_QUERIES_PER_ITER]
        except Exception as exc:
            logger.warning("Query generation failed (iter %d): %s", iteration, exc)
            new_queries = [topic] if iteration == 0 else []

        all_queries.extend(new_queries)

        for query in new_queries:
            await _emit(session_id, "query", query=query)
            chunks = await hybrid_search(query, session_id, db, top_k=8)
            all_chunks.extend(chunks)
            await _emit(session_id, "retrieved", query=query, count=len(chunks))
            await asyncio.sleep(0)  # yield to event loop

    # Deduplicate and rank by RRF score
    all_chunks = _dedup(all_chunks)
    all_chunks.sort(key=lambda c: c.score, reverse=True)

    # ── Phase 2: syllabus synthesis ───────────────────────────────────────────
    await _emit(session_id, "status", message="Synthesising syllabus…")

    context = _format_context(all_chunks[:_TOP_CHUNKS])

    try:
        syllabus = await llm.complete_json(
            messages=[
                {"role": "system", "content": SYLLABUS_SYSTEM},
                {"role": "user", "content": syllabus_user(topic, context)},
            ],
            schema=Syllabus,
            temperature=0.2,
        )
    except Exception as exc:
        raise RuntimeError(f"Syllabus generation failed: {exc}") from exc

    # ── Phase 3: embed chunks + persist ──────────────────────────────────────
    await _emit(session_id, "status", message="Embedding knowledge chunks…")

    top_chunks = all_chunks[:30]
    if top_chunks:
        try:
            embeddings = await embed([c.text for c in top_chunks])
            for chunk, emb in zip(top_chunks, embeddings):
                db.add(
                    KnowledgeChunk(
                        session_id=session_id,
                        source_type=chunk.source_type,
                        source_title=chunk.title,
                        source_url=chunk.source_url,
                        content=chunk.text,
                        embedding=emb,
                    )
                )
        except Exception as exc:
            logger.warning("Chunk embedding failed: %s — storing without vectors", exc)
            for chunk in top_chunks:
                db.add(
                    KnowledgeChunk(
                        session_id=session_id,
                        source_type=chunk.source_type,
                        source_title=chunk.title,
                        source_url=chunk.source_url,
                        content=chunk.text,
                    )
                )

    # Persist syllabus sections
    for i, sec in enumerate(syllabus.sections):
        db.add(
            SyllabusSection(
                session_id=session_id,
                position=i,
                title=sec.title,
                summary=sec.summary,
                learning_objectives=sec.learning_objectives,
                key_concepts=sec.key_concepts,
                status="pending",
            )
        )

    # Mark session done
    session_obj = await db.get(ResearchSession, session_id)
    if session_obj:
        session_obj.status = "done"

    await db.commit()

    await _emit(session_id, "done", session_id=str(session_id))
    logger.info("Research pipeline complete for session %s", session_id)
