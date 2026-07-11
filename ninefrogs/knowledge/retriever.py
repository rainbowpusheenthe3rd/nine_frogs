"""Hybrid retriever: BM25 (Wikipedia) + pgvector (session chunks), fused with RRF.

When a collection_id is supplied, collection DocumentChunks replace Wikipedia
BM25 as the primary knowledge source.  Session-scoped KnowledgeChunks are still
used for the vector leg in either mode.

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


# ── collection vector search ───────────────────────────────────────────────────

async def _collection_vector_search(
    query_vec: list[float],
    collection_id: uuid.UUID,
    db: AsyncSession,
    top_k: int,
) -> list[RetrievedChunk]:
    """Vector search over DocumentChunks for a specific collection."""
    from db.models import Document, DocumentChunk

    try:
        stmt = (
            select(DocumentChunk, Document.title, Document.source_uri, Document.source_type)
            .join(Document, DocumentChunk.document_id == Document.id)
            .where(DocumentChunk.collection_id == collection_id)
            .where(DocumentChunk.embedding.is_not(None))
            .order_by(DocumentChunk.embedding.cosine_distance(query_vec))
            .limit(top_k)
        )
        result = await db.execute(stmt)
        rows = result.all()
        return [
            RetrievedChunk(
                title=doc_title or "",
                text=chunk.content,
                source_type=doc_source_type or "collection",
                source_url=doc_source_uri,
            )
            for chunk, doc_title, doc_source_uri, doc_source_type in rows
        ]
    except Exception as exc:
        logger.warning("Collection vector search failed: %s", exc)
        return []


# ── public API ────────────────────────────────────────────────────────────────

async def hybrid_search(
    query: str,
    session_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 15,
    collection_id: uuid.UUID | None = None,
) -> list[RetrievedChunk]:
    """BM25 + pgvector hybrid search with RRF fusion.

    If collection_id is provided, collection DocumentChunks replace Wikipedia
    BM25 as the primary retrieval source.
    """
    loop = asyncio.get_event_loop()

    try:
        vecs = await embed([query])
        query_vec = vecs[0]
    except Exception as exc:
        logger.warning("Embedding failed: %s", exc)
        query_vec = None

    if collection_id is not None:
        # Collection mode: vector search over DocumentChunks (no BM25)
        if query_vec is not None:
            primary_hits = await _collection_vector_search(query_vec, collection_id, db, top_k)
        else:
            primary_hits = []
        # Still run session-scoped vector search as a secondary signal if chunks exist
        vec_hits = await _vector_search(query_vec, session_id, db, top_k) if query_vec else []
        # Treat collection hits as "bm25" side of RRF (rank-ordered, no real BM25 score)
        bm25_like = [
            {"title": c.title, "text": c.text, "source_type": c.source_type, "source_url": c.source_url}
            for c in primary_hits
        ]
        merged = _rrf_merge(bm25_like, vec_hits, top_k)
    else:
        # Wikipedia mode: BM25 + session vector search
        bm25_hits = await loop.run_in_executor(None, lambda: bm25_search(query, top_k=top_k))
        vec_hits = await _vector_search(query_vec, session_id, db, top_k) if query_vec else []
        merged = _rrf_merge(bm25_hits, vec_hits, top_k)

    return merged


async def cross_direction_search(
    question: str,
    section_title: str,
    session_id: uuid.UUID,
    db: AsyncSession,
    top_k: int = 8,
    collection_id: uuid.UUID | None = None,
) -> list[RetrievedChunk]:
    """Cross-direction retrieval for flashcard generation.

    Runs a forward query (the question) and a backward query (answer-angle),
    merges with deduplication, and returns top_k.
    """
    forward = await hybrid_search(question, session_id, db, top_k=top_k, collection_id=collection_id)

    # Backward: rephrase to retrieve from the "definition / explanation" angle
    backward_q = f"{section_title} — {question}"
    backward = await hybrid_search(backward_q, session_id, db, top_k=top_k, collection_id=collection_id)

    # Deduplicate: forward first (higher precision), then add new from backward
    seen: set[str] = set()
    merged: list[RetrievedChunk] = []
    for c in forward + backward:
        if c.key not in seen:
            seen.add(c.key)
            merged.append(c)

    merged.sort(key=lambda c: c.score, reverse=True)
    return merged[:top_k]
