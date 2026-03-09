"""AnkiConnect HTTP client.

Requires Anki running with the AnkiConnect add-on (code: 2055492159).
All calls use the JSON-RPC v6 protocol at ANKI_URL (default localhost:8765).
"""
from __future__ import annotations

import httpx

from config import settings


class AnkiConnectError(Exception):
    pass


async def _invoke(action: str, **params: object) -> object:
    async with httpx.AsyncClient(timeout=10) as client:
        resp = await client.post(
            settings.anki_url,
            json={"action": action, "version": 6, "params": params},
        )
    data = resp.json()
    if data.get("error"):
        raise AnkiConnectError(data["error"])
    return data["result"]


async def check_connection() -> bool:
    try:
        await _invoke("version")
        return True
    except Exception:
        return False


async def ensure_deck(deck_name: str) -> None:
    await _invoke("createDeck", deck=deck_name)


async def add_notes(deck: str, cards: list[dict]) -> list[int | None]:
    """Push cards to Anki.  Returns list of note IDs (None if duplicate)."""
    notes = [
        {
            "deckName": deck,
            "modelName": "Basic",
            "fields": {
                "Front": c["front"],
                "Back": c["back"] + (f"\n<br><i>💡 {c['hint']}</i>" if c.get("hint") else ""),
            },
            "tags": c.get("tags", []),
            "options": {"allowDuplicate": False},
        }
        for c in cards
    ]
    result = await _invoke("addNotes", notes=notes)
    return list(result)  # type: ignore[arg-type]
