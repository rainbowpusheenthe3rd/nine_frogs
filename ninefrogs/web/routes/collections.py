"""Routes for document collection management."""
from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Form, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from db.models import Document, DocumentChunk, DocumentCollection
from knowledge.ingest import ingest_crawl, ingest_text
from knowledge.repo import ingest_repo
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


# ── list ──────────────────────────────────────────────────────────────────────

@router.get("/")
async def collections_list(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(DocumentCollection).order_by(desc(DocumentCollection.created_at))
    )
    collections = result.scalars().all()
    return templates.TemplateResponse(
        "collections.html", {"request": request, "collections": collections}
    )


# ── create ────────────────────────────────────────────────────────────────────

@router.post("/new")
async def create_collection(
    name: str = Form(...),
    description: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    collection = DocumentCollection(
        name=name.strip(),
        description=description.strip() or None,
    )
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return RedirectResponse(f"/collections/{collection.id}", status_code=303)


# ── detail ────────────────────────────────────────────────────────────────────

@router.get("/{collection_id}")
async def collection_detail(
    collection_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    collection = await db.get(DocumentCollection, collection_id)
    if not collection:
        return templates.TemplateResponse(
            "error.html", {"request": request, "msg": "Collection not found"}, status_code=404
        )

    doc_result = await db.execute(
        select(Document)
        .where(Document.collection_id == collection_id)
        .order_by(desc(Document.added_at))
    )
    documents = doc_result.scalars().all()

    chunk_count_result = await db.execute(
        select(DocumentChunk.id).where(DocumentChunk.collection_id == collection_id)
    )
    chunk_count = len(chunk_count_result.all())

    return templates.TemplateResponse(
        "collection_detail.html",
        {
            "request": request,
            "collection": collection,
            "documents": documents,
            "chunk_count": chunk_count,
            "config": settings,
        },
    )


# ── ingest: paste ─────────────────────────────────────────────────────────────

@router.post("/{collection_id}/ingest/paste")
async def ingest_paste(
    collection_id: uuid.UUID,
    title: str = Form(...),
    content: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    await ingest_text(
        db=db,
        collection_id=collection_id,
        title=title.strip(),
        source_type="paste",
        raw_text=content,
        source_uri=None,
    )
    return RedirectResponse(f"/collections/{collection_id}", status_code=303)


# ── ingest: file upload ───────────────────────────────────────────────────────

@router.post("/{collection_id}/ingest/upload")
async def ingest_upload(
    collection_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    raw_bytes = await file.read()
    filename = file.filename or "uploaded_file"

    # Plain text / markdown
    if filename.lower().endswith((".txt", ".md")):
        text = raw_bytes.decode("utf-8", errors="replace")

    # PDF — extract via pypdf if available, else treat as binary and skip
    elif filename.lower().endswith(".pdf"):
        try:
            import io
            from pypdf import PdfReader
            reader = PdfReader(io.BytesIO(raw_bytes))
            pages = [p.extract_text() or "" for p in reader.pages]
            text = "\n\n".join(pages)
        except ImportError:
            return RedirectResponse(
                f"/collections/{collection_id}?error=pypdf+not+installed", status_code=303
            )

    else:
        # Attempt UTF-8 decode for any other text-like format
        text = raw_bytes.decode("utf-8", errors="replace")

    await ingest_text(
        db=db,
        collection_id=collection_id,
        title=filename,
        source_type="upload",
        raw_text=text,
        source_uri=filename,
    )
    return RedirectResponse(f"/collections/{collection_id}", status_code=303)


# ── ingest: crawl ─────────────────────────────────────────────────────────────

@router.post("/{collection_id}/ingest/crawl")
async def ingest_crawl_route(
    collection_id: uuid.UUID,
    seed_url: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Run crawl as background task so the response returns immediately
    async def _run():
        from db.engine import async_session_factory
        async with async_session_factory() as bg_db:
            await ingest_crawl(bg_db, collection_id, seed_url)

    asyncio.create_task(_run())
    return RedirectResponse(f"/collections/{collection_id}?crawling=1", status_code=303)


# ── ingest: repo ──────────────────────────────────────────────────────────────

@router.post("/{collection_id}/ingest/repo")
async def ingest_repo_route(
    collection_id: uuid.UUID,
    repo_path: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Walk the repo in a background task so the response returns immediately
    async def _run():
        from db.engine import async_session_factory
        async with async_session_factory() as bg_db:
            await ingest_repo(bg_db, collection_id, repo_path.strip())

    asyncio.create_task(_run())
    return RedirectResponse(f"/collections/{collection_id}?ingesting=1", status_code=303)


# ── delete collection ─────────────────────────────────────────────────────────

@router.post("/{collection_id}/delete")
async def delete_collection(
    collection_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    collection = await db.get(DocumentCollection, collection_id)
    if collection:
        await db.delete(collection)
        await db.commit()
    return RedirectResponse("/collections/", status_code=303)
