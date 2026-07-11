"""Syllabus-drill integration — generate Nine Frogs flashcards from a drill syllabus level.

Flow:
  GET  /drills/            — picker: choose subject + level
  POST /drills/generate    — create ResearchSession + SyllabusSections from YAML, trigger card gen
"""
from __future__ import annotations

import asyncio

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ResearchSession, SyllabusSection
from lab.subjects import (
    domain_display_name,
    group_by_domain,
    load_all_syllabuses,
    resolve_prerequisites,
)
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


def _get_level(syllabus: dict, level: int) -> dict | None:
    for lvl in syllabus.get("levels", []):
        if lvl["level"] == level:
            return lvl
    return None


# ── Routes ────────────────────────────────────────────────────────────────────

@router.get("/")
async def drill_picker(request: Request):
    syllabuses = load_all_syllabuses()
    resolve_prerequisites(syllabuses)  # annotate cross-links linked|proposed
    grouped = group_by_domain(syllabuses)
    domain_names = {d: domain_display_name(d) for d in grouped}
    return templates.TemplateResponse(
        "drills_picker.html",
        {
            "request": request,
            "grouped": grouped,
            "domain_names": domain_names,
        },
    )


@router.post("/generate")
async def generate_drill_cards(
    subject: str = Form(...),
    level: int = Form(...),
    db: AsyncSession = Depends(get_db),
):
    syllabuses = load_all_syllabuses()
    if subject not in syllabuses:
        return HTMLResponse(f"Subject '{subject}' not found.", status_code=404)

    syllabus = syllabuses[subject]
    lvl_data = _get_level(syllabus, level)
    if not lvl_data:
        return HTMLResponse(f"Level {level} not found in {subject}.", status_code=404)

    topic = f"{syllabus['title']} — Level {level}: {lvl_data['title']}"
    session = ResearchSession(topic=topic, status="done")
    db.add(session)
    await db.flush()

    section = SyllabusSection(
        session_id=session.id,
        position=1,
        drill_level=level,
        title=lvl_data["title"],
        summary=lvl_data.get("description", "").strip().replace("\n", " "),
        learning_objectives=lvl_data.get("objectives", []),
        key_concepts=lvl_data.get("concepts", []),
        status="accepted",
    )
    db.add(section)
    await db.commit()
    await db.refresh(session)

    session.status = "generating_cards"
    await db.commit()

    from flashcards.generator import generate_for_session
    asyncio.create_task(generate_for_session(session.id))

    return RedirectResponse(f"/cards/{session.id}", status_code=303)
