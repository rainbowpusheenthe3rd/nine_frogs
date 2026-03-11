"""Wiki status endpoint — polled by the homepage banner."""
from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import JSONResponse

router = APIRouter()


@router.get("/wiki/ready")
async def wiki_ready_status() -> JSONResponse:
    """Return current Wikipedia index loading state.

    Response shape:
        { "status": "idle|downloading|parsing|indexing|ready|error",
          "pct": 0-100,
          "articles": int,
          "message": str }
    """
    from knowledge.wikipedia import wiki_state
    return JSONResponse(wiki_state)
