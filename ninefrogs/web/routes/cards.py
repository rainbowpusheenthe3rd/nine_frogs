from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Flashcard, SyllabusSection
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


@router.get("/{session_id}")
async def cards_review(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # Next pending card
    result = await db.execute(
        select(Flashcard)
        .where(Flashcard.session_id == session_id)
        .where(Flashcard.status == "pending")
        .order_by(Flashcard.created_at)
        .limit(1)
    )
    card = result.scalar_one_or_none()

    total = (
        await db.execute(
            select(func.count(Flashcard.id)).where(Flashcard.session_id == session_id)
        )
    ).scalar()

    approved = (
        await db.execute(
            select(func.count(Flashcard.id))
            .where(Flashcard.session_id == session_id)
            .where(Flashcard.status == "approved")
        )
    ).scalar()

    rejected = (
        await db.execute(
            select(func.count(Flashcard.id))
            .where(Flashcard.session_id == session_id)
            .where(Flashcard.status == "rejected")
        )
    ).scalar()

    section = None
    if card:
        section = await db.get(SyllabusSection, card.section_id)

    return templates.TemplateResponse(
        "card_review.html",
        {
            "request": request,
            "session_id": session_id,
            "card": card,
            "section": section,
            "total": total or 0,
            "approved": approved or 0,
            "rejected": rejected or 0,
            "pending": (total or 0) - (approved or 0) - (rejected or 0),
        },
    )


@router.post("/{card_id}/approve")
async def approve_card(card_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    card = await db.get(Flashcard, card_id)
    if card:
        card.status = "approved"
        await db.commit()
    return HTMLResponse('<span class="flash-result approved">✓</span>')


@router.post("/{card_id}/reject")
async def reject_card(card_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    card = await db.get(Flashcard, card_id)
    if card:
        card.status = "rejected"
        await db.commit()
    return HTMLResponse('<span class="flash-result rejected">✗</span>')
