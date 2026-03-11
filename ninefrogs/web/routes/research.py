from __future__ import annotations

import json
from loguru import logger
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import ResearchSession
from research.events import event_store
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


@router.get("/{session_id}")
async def research_page(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    session = await db.get(ResearchSession, session_id)
    if not session:
        return templates.TemplateResponse(
            "error.html", {"request": request, "msg": "Session not found"}, status_code=404
        )
    return templates.TemplateResponse(
        "research_progress.html", {"request": request, "session": session}
    )


@router.get("/{session_id}/stream")
async def research_stream(session_id: uuid.UUID):
    async def generator():
        try:
            async for event in event_store.subscribe(session_id):
                yield event.to_sse()
        except Exception as exc:
            logger.warning("SSE error for session %s: %s", session_id, exc)
            yield f"data: {json.dumps({'type': 'error', 'message': str(exc)})}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
