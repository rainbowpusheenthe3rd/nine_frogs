"""Document ingestion pipeline.

Accepts raw text (from any source — upload, crawl, paste, API, etc.),
chunks it, computes SHA-256 hashes for deduplication, embeds each chunk,
and stores everything in document_collections / documents / document_chunks.

Public API
----------
ingest_text(db, collection_id, title, source_type, source_uri, raw_text)
    → Document | None   (None if content_sha already exists in collection)

search_collection(collection_id, query_embedding, db, top_k)
    → list[DocumentChunk]  ordered by cosine similarity
"""
from __future__ import annotations

import hashlib
import uuid
from typing import Sequence

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Document, DocumentChunk, DocumentCollection
from embeddings import embed


# ── chunking ──────────────────────────────────────────────────────────────────

_CHUNK_SIZE = 400    # target words per chunk
_CHUNK_OVERLAP = 80  # words of overlap between consecutive chunks


def _chunk_text(text: str) -> list[str]:
    """Split text into overlapping word-window chunks."""
    words = text.split()
    if not words:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + _CHUNK_SIZE, len(words))
        chunks.append(" ".join(words[start:end]))
        if end == len(words):
            break
        start += _CHUNK_SIZE - _CHUNK_OVERLAP

    return chunks


def _sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


# ── ingestion ─────────────────────────────────────────────────────────────────

async def ingest_text(
    db: AsyncSession,
    collection_id: uuid.UUID,
    title: str,
    source_type: str,
    raw_text: str,
    source_uri: str | None = None,
) -> Document | None:
    """Ingest raw text into a collection.

    Returns the created Document, or None if this content was already ingested
    (matched by content_sha within the same collection).
    """
    content_sha = _sha256(raw_text)

    # Dedup: skip if this exact content is already in the collection
    existing = await db.execute(
        select(Document).where(
            Document.collection_id == collection_id,
            Document.content_sha == content_sha,
        )
    )
    if existing.scalar_one_or_none():
        logger.info("Skipping duplicate document '%s' (sha=%s…)", title, content_sha[:12])
        return None

    # Create document record
    doc = Document(
        collection_id=collection_id,
        title=title,
        source_type=source_type,
        source_uri=source_uri,
        content_sha=content_sha,
    )
    db.add(doc)
    await db.flush()  # get doc.id without committing

    # Chunk
    raw_chunks = _chunk_text(raw_text)
    if not raw_chunks:
        logger.warning("Document '%s' produced no chunks — skipping", title)
        return None

    logger.info("Ingesting '%s': %d chunks to embed", title, len(raw_chunks))

    # Embed all chunks in one batch
    try:
        embeddings = await embed(raw_chunks)
    except Exception as exc:
        logger.warning("Embedding failed for '%s': %s — storing without vectors", title, exc)
        embeddings = [None] * len(raw_chunks)

    # Persist chunks
    for position, (text, emb) in enumerate(zip(raw_chunks, embeddings)):
        db.add(
            DocumentChunk(
                document_id=doc.id,
                collection_id=collection_id,
                content=text,
                position=position,
                content_sha=_sha256(text),
                embedding=emb,
            )
        )

    await db.commit()
    logger.info("Ingested document '%s' (%d chunks)", title, len(raw_chunks))
    return doc


# ── crawl ingestion ───────────────────────────────────────────────────────────

async def ingest_crawl(
    db: AsyncSession,
    collection_id: uuid.UUID,
    seed_url: str,
    max_pages: int | None = None,
) -> list[Document]:
    """Crawl a URL and ingest all discovered pages into a collection."""
    from knowledge.crawler import crawl

    pages = await crawl(seed_url, max_pages=max_pages)
    docs: list[Document] = []
    for page in pages:
        doc = await ingest_text(
            db=db,
            collection_id=collection_id,
            title=page.get("title") or page["url"],
            source_type="crawl",
            source_uri=page["url"],
            raw_text=page.get("text", ""),
        )
        if doc:
            docs.append(doc)
    return docs


# ── vector search ─────────────────────────────────────────────────────────────

async def search_collection(
    collection_id: uuid.UUID,
    query_embedding: list[float],
    db: AsyncSession,
    top_k: int = 10,
) -> Sequence[DocumentChunk]:
    """Return top-k chunks from a collection ordered by cosine similarity."""
    result = await db.execute(
        select(DocumentChunk)
        .where(
            DocumentChunk.collection_id == collection_id,
            DocumentChunk.embedding.isnot(None),
        )
        .order_by(DocumentChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
    )
    return result.scalars().all()
