"""FastAPI application factory."""
from __future__ import annotations

import asyncio

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from loguru import logger

from config import settings


def create_app() -> FastAPI:
    from web.routes import anki as anki_routes
    from web.routes import cards, index, research, syllabus, wiki

    app = FastAPI(title="Nine Frogs", docs_url=None, redoc_url=None)
    app.mount("/static", StaticFiles(directory="web/static"), name="static")

    app.include_router(index.router)
    app.include_router(wiki.router)
    app.include_router(research.router, prefix="/research")
    app.include_router(syllabus.router, prefix="/syllabus")
    app.include_router(cards.router, prefix="/cards")
    app.include_router(anki_routes.router, prefix="/anki")

    @app.on_event("startup")
    async def startup() -> None:
        logger.info("🐸 Nine Frogs starting…")

        from db.engine import init_db
        await init_db()
        logger.info("Database ready.")

        from knowledge.wikipedia import load_wikipedia
        asyncio.create_task(load_wikipedia())

        logger.info(
            "Server running at http://%s:%s", settings.web_host, settings.web_port
        )

    return app
