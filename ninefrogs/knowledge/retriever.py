"""Hybrid retriever: BM25 (Wikipedia) + pgvector (session chunks), fused with RRF.

Cross-direction retrieval for flashcard generation runs two queries:
  forward  — the question as asked
  backward — a rephrased "definition of / process of" angle
Results are merged with Reciprocal Rank Fusion before returning.
"""
from __future__ import annotations

import asyncio
from loguru import logger
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from embeddings import embed
from knowledge.wikipedia import bm25_search


_RRF_K = 60


@dataclass
class RetrievedChunk:
    title: str
    text: str
    source_type: str        # wikipedia | web
    source_url: str | None
    score: float = field(default=0.0)

    @property
    def key(self) -> str:
        return self.title or (self.source_url or "") or self.text[:80]


# ── vector search ─────────────────────────────────────────────────────────────

async def _vector_search(
    query_vec: list[float],
    session_id: uuid.UUID,
    db: AsyncSession,
    top_k: int,
) -> list[RetrievedChunk]:
    from db.models import KnowledgeChunk

    try:
        stmt = (
            select(KnowledgeChunk)
            .where(KnowledgeChunk.session_id == session_id)
            .where(KnowledgeChunk.embedding.is_not(None))
            .order_by(KnowledgeChunk.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )
        result = await db.execute(stmt)
        rows = result.scalars().all()
        return [
            RetrievedChunk(
                title=r.source_title or "",
                text=r.content,
                source_type=r.source_type,
                source_url=r.source_url,
            )
            for r in rows
        ]
    except Exception as exc:
        logger.warning("Vector search failed: %s", exc)
        return []


# ── RRF fusion ────────────────────────────────────────────────────────────────

def _rrf_merge(
    bm25_hits: list[dict],
    vec_hits: list[RetrievedChunk],
    top_k: int,
) -> list[RetrievedChunk]:
    scores: dict[str, float] = {}
    chunks: dict[str, RetrievedChunk] = {}

    for rank, hit in enumerate(bm25_hits):
        c = RetrievedChunk(
            title=hit["title"],
            text=hit["text"],
            source_type=hit["source_type"],
            source_url=hit.get("source_url"),
        )
        k = c.key
        scores[k] = scores.get(k, 0.0) + 1.0 / (_RRF_K + rank + 1)
        chunks[k] = c

    for rank, c in enumerate(vec_hits):
        k = c.key
        scores[k] = scores.get(k, 0.0) + 1.0 / (_RRF_K + rank + 1)
        if k not in chunks:
            chunks[k] = c

    for k, c in chunks.items():
        c.score = scores[k]

    return sorted(chunks.values(), key=lambda c: c.score, reverse=True)[:top_k]


# ── public API ────────────────────────────────────────────────────────────────

async def hybrid_search(
    query: str,
    session_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 15,
) -> list[RetrievedChunk]:
    """BM25 + pgvector hybrid search with RRF fusion."""
    loop = asyncio.get_event_loop()

    # BM25 scoring is CPU-bound — run in executor so we don't block the event loop
    bm25_hits = await loop.run_in_executor(None, lambda: bm25_search(query, top_k=top_k))

    try:
        vecs = await embed([query])
        vec_hits = await _vector_search(vecs[0], session_id, db, top_k)
    except Exception as exc:
        logger.warning("Embedding failed, falling back to BM25 only: %s", exc)
        vec_hits = []

    merged = _rrf_merge(bm25_hits, vec_hits, top_k)
    return merged


async def cross_direction_search(
    question: str,
    section_title: str,
    session_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 8,
) -> list[RetrievedChunk]:
    """Cross-direction retrieval for flashcard generation.

    Runs a forward query (the question) and a backward query (answer-angle),
    merges with deduplication, and returns top_k.
    """
    forward = await hybrid_search(question, session_id, db, top_k=top_k)

    # Backward: rephrase to retrieve from the "definition / explanation" angle
    backward_q = f"{section_title} — {question}"
    backward = await hybrid_search(backward_q, session_id, db, top_k=top_k)

    # Deduplicate: forward first (higher precision), then add new from backward
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []
    for c in forward + backward:
        if c.key not in seen:
            seen.add(c.key)
            merged.append(c)

    merged.sort(key=lambda c: c.score, reverse=True)
    return merged[:top_k]
