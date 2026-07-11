from __future__ import annotations

import asyncio
import uuid as uuid_lib

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import DocumentCollection, ResearchSession
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


@router.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    sessions_result = await db.execute(
        select(ResearchSession).order_by(desc(ResearchSession.created_at)).limit(12)
    )
    sessions = sessions_result.scalars().all()

    collections_result = await db.execute(
        select(DocumentCollection).order_by(DocumentCollection.name)
    )
    collections = collections_result.scalars().all()

    return templates.TemplateResponse(
        "index.html",
        {"request": request, "sessions": sessions, "collections": collections},
    )


@router.post("/start")
async def start_research(
    topic: str = Form(...),
    collection_id: str = Form(""),
    db: AsyncSession = Depends(get_db),
):
    cid: uuid_lib.UUID | None = None
    if collection_id.strip():
        try:
            cid = uuid_lib.UUID(collection_id.strip())
        except ValueError:
            pass

    session = ResearchSession(topic=topic.strip(), status="running", collection_id=cid)
    db.add(session)
    await db.commit()
    await db.refresh(session)

    from research.events import event_store
    from research.pipeline import run_research

    event_store.create(session.id)
    asyncio.create_task(run_research(session.id))

    return RedirectResponse(f"/research/{session.id}", status_code=303)
