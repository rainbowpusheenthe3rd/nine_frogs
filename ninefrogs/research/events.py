"""SSE event store for the research pipeline.

Each research session gets a queue.  Consumers call `subscribe()` which
first replays historical events (for reconnect), then streams live ones.
The module-level `event_store` singleton is shared across all routes.
"""
from __future__ import annotations

import asyncio
import json
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator


@dataclass
class ResearchEvent:
    type: str      # status | query | retrieved | synthesising | done | error
    payload: dict = field(default_factory=dict)

    def to_sse(self) -> str:
        return f"data: {json.dumps({'type': self.type, **self.payload})}\n\n"


class EventStore:
    def __init__(self) -> None:
        self._history: dict[uuid.UUID, list[ResearchEvent]] = {}
        self._queues: dict[uuid.UUID, list[asyncio.Queue]] = {}

    def create(self, session_id: uuid.UUID) -> None:
        self._history[session_id] = []
        self._queues[session_id] = []

    async def publish(self, session_id: uuid.UUID, event: ResearchEvent) -> None:
        self._history.setdefault(session_id, []).append(event)
        for q in self._queues.get(session_id, []):
            await q.put(event)

    async def subscribe(self, session_id: uuid.UUID) -> AsyncIterator[ResearchEvent]:
        # Replay history first so reconnecting clients catch up
        for event in self._history.get(session_id, []):
            yield event
            if event.type == "done":
                return

        # Then stream live events
        q: asyncio.Queue[ResearchEvent | None] = asyncio.Queue()
        self._queues.setdefault(session_id, []).append(q)
        try:
            while True:
                event = await asyncio.wait_for(q.get(), timeout=120.0)
                if event is None:
                    break
                yield event
                if event.type in ("done", "error"):
                    break
        except asyncio.TimeoutError:
            return
        finally:
            try:
                self._queues[session_id].remove(q)
            except (KeyError, ValueError):
                pass

    def cleanup(self, session_id: uuid.UUID) -> None:
        """Signal all subscribers to stop and clear history."""
        for q in self._queues.pop(session_id, []):
            q.put_nowait(None)
        self._history.pop(session_id, None)


# module-level singleton imported everywhere
event_store = EventStore()
