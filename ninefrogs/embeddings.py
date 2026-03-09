"""Sentence-transformer embedding singleton.

Runs on CPU by default (EMBED_DEVICE=cpu in .env) so Ollama keeps full VRAM.
Set EMBED_DEVICE=cuda in .env to use GPU (needs ~500MB VRAM).
"""
from __future__ import annotations

import asyncio
import logging

from config import settings

logger = logging.getLogger(__name__)

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        logger.info("Loading embedding model: %s on %s", settings.embed_model, settings.embed_device)
        _model = SentenceTransformer(settings.embed_model, device=settings.embed_device)
        logger.info("Embedding model ready.")
    return _model


async def embed(texts: list[str]) -> list[list[float]]:
    """Embed a list of texts. Returns list of float vectors (normalized)."""
    if not texts:
        return []
    loop = asyncio.get_event_loop()
    model = _get_model()
    result = await loop.run_in_executor(
        None,
        lambda: model.encode(texts, normalize_embeddings=True).tolist(),
    )
    return result


async def embed_one(text: str) -> list[float]:
    vecs = await embed([text])
    return vecs[0]
