from __future__ import annotations

import asyncio
import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ResearchSession, SyllabusSection
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


@router.get("/{session_id}")
async def syllabus_review(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ResearchSession, session_id)
    result = await db.execute(
        select(SyllabusSection)
        .where(SyllabusSection.session_id == session_id)
        .order_by(SyllabusSection.position)
    )
    sections = result.scalars().all()
    return templates.TemplateResponse(
        "syllabus_review.html",
        {"request": request, "session": session, "sections": sections},
    )


@router.post("/section/{section_id}/accept")
async def accept_section(section_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    section = await db.get(SyllabusSection, section_id)
    if section:
        section.status = "accepted"
        await db.commit()
    return HTMLResponse('<span class="status-badge accepted">✓ Accepted</span>')


@router.post("/section/{section_id}/reject")
async def reject_section(section_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    section = await db.get(SyllabusSection, section_id)
    if section:
        section.status = "rejected"
        await db.commit()
    return HTMLResponse('<span class="status-badge rejected">✗ Rejected</span>')


@router.post("/section/{section_id}/edit")
async def edit_section(
    section_id: uuid.UUID,
    title: str = Form(...),
    summary: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    section = await db.get(SyllabusSection, section_id)
    if section:
        section.title = title.strip()
        section.summary = summary.strip()
        section.status = "accepted"
        await db.commit()
    return HTMLResponse('<span class="status-badge accepted">✓ Saved</span>')


@router.post("/{session_id}/generate-cards")
async def generate_cards(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    session = await db.get(ResearchSession, session_id)
    if session:
        session.status = "generating_cards"
        await db.commit()

    from flashcards.generator import generate_for_session

    asyncio.create_task(generate_for_session(session_id))
    return RedirectResponse(f"/cards/{session_id}", status_code=303)
