from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ResearchSession
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


@router.get("/")
async def home(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(ResearchSession).order_by(desc(ResearchSession.created_at)).limit(12)
    )
    sessions = result.scalars().all()
    return templates.TemplateResponse("index.html", {"request": request, "sessions": sessions})


@router.post("/start")
async def start_research(
    topic: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    session = ResearchSession(topic=topic.strip(), status="running")
    db.add(session)
    await db.commit()
    await db.refresh(session)

    from research.events import event_store
    from research.pipeline import run_research

    event_store.create(session.id)
    asyncio.create_task(run_research(session.id))

    return RedirectResponse(f"/research/{session.id}", status_code=303)
