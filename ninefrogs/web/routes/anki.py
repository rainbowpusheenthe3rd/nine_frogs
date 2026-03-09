from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from anki.client import add_notes, check_connection, ensure_deck
from config import settings
from db.models import Flashcard
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


@router.get("/export/{session_id}")
async def export_page(
    session_id: uuid.UUID,
    request: Request,
    done: str = "",
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(Flashcard)
        .where(Flashcard.session_id == session_id)
        .where(Flashcard.status == "approved")
    )
    cards = result.scalars().all()
    anki_ok = await check_connection()

    return templates.TemplateResponse(
        "anki_export.html",
        {
            "request": request,
            "session_id": session_id,
            "cards": cards,
            "card_count": len(cards),
            "anki_connected": anki_ok,
            "default_deck": settings.anki_default_deck,
            "done": done == "1",
        },
    )


@router.post("/export/{session_id}")
async def do_export(
    session_id: uuid.UUID,
    deck_name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    # Only push cards not yet exported
    result = await db.execute(
        select(Flashcard)
        .where(Flashcard.session_id == session_id)
        .where(Flashcard.status == "approved")
        .where(Flashcard.anki_note_id.is_(None))
    )
    cards = result.scalars().all()

    await ensure_deck(deck_name)
    card_dicts = [
        {"front": c.front, "back": c.back, "hint": c.hint, "tags": c.tags} for c in cards
    ]
    note_ids = await add_notes(deck_name, card_dicts)

    for card, note_id in zip(cards, note_ids):
        if note_id:
            card.anki_note_id = note_id
    await db.commit()

    return RedirectResponse(f"/anki/export/{session_id}?done=1", status_code=303)
