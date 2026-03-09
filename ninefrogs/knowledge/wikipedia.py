"""Wikipedia knowledge source.

Loads NeuML/txtai-wikipedia-slim (~100k articles) from HuggingFace datasets,
builds a BM25 index over title+text, and optionally a NetworkX graph for
neighbourhood retrieval.

The index is pickled to WIKI_CACHE_DIR on first run (takes ~2 min, ~500 MB
download).  Subsequent startups load from cache in seconds.

`wiki_ready` is an asyncio.Event set when the index is built — callers
`await wiki_ready.wait()` before issuing queries.
"""
from __future__ import annotations

import asyncio
import logging
import pickle
from pathlib import Path

import networkx as nx

from config import settings

logger = logging.getLogger(__name__)

# ── module-level singletons ───────────────────────────────────────────────────
_bm25 = None
_corpus: list[dict] = []       # [{title, text, idx}]
_graph: nx.Graph = nx.Graph()
wiki_ready = asyncio.Event()


# ── index building (CPU-bound, runs in thread pool) ───────────────────────────

def _build_index(dataset) -> tuple:
    """Build BM25 index from a HuggingFace dataset."""
    from rank_bm25 import BM25Okapi

    corpus: list[dict] = []
    tokenized: list[list[str]] = []

    for i, article in enumerate(dataset):
        title = article.get("title", "") or ""
        text = (article.get("text", "") or "")[:2000]
        combined = f"{title} {text}"
        tokenized.append(combined.lower().split())
        corpus.append({"title": title, "text": text, "idx": i})
        if i % 10_000 == 0 and i > 0:
            logger.info("  Indexed %d / %d articles…", i, len(dataset))

    bm25 = BM25Okapi(tokenized)
    return bm25, corpus


# ── public async loader ───────────────────────────────────────────────────────

async def load_wikipedia() -> None:
    """Download / load the Wikipedia dataset and build BM25 index.

    Safe to call at startup as an asyncio task.
    """
    global _bm25, _corpus, _graph

    if not settings.wiki_enabled:
        logger.info("Wikipedia disabled (WIKI_ENABLED=false).")
        wiki_ready.set()
        return

    cache_dir = Path(settings.wiki_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "wiki_bm25.pkl"

    # ── try loading from cache ────────────────────────────────────────────────
    if cache_file.exists():
        logger.info("Loading Wikipedia index from cache…")
        try:
            loop = asyncio.get_event_loop()
            _bm25, _corpus = await loop.run_in_executor(
                None,
                lambda: pickle.load(open(cache_file, "rb")),
            )
            logger.info("Loaded %s Wikipedia articles from cache.", f"{len(_corpus):,}")
            wiki_ready.set()
            return
        except Exception as exc:
            logger.warning("Cache load failed (%s) — rebuilding.", exc)

    # ── download + build ──────────────────────────────────────────────────────
    logger.info("Downloading %s — first run may take a few minutes…", settings.wiki_dataset)
    try:
        from datasets import load_dataset

        loop = asyncio.get_event_loop()
        ds = await loop.run_in_executor(
            None,
            lambda: load_dataset(
                settings.wiki_dataset,
                split="train",
                trust_remote_code=True,
            ),
        )
        logger.info("Building BM25 index over %s articles…", f"{len(ds):,}")
        _bm25, _corpus = await loop.run_in_executor(None, _build_index, ds)

        # persist cache
        await loop.run_in_executor(
            None,
            lambda: pickle.dump((_bm25, _corpus), open(cache_file, "wb")),
        )
        logger.info("Wikipedia index cached to %s.", cache_file)

    except Exception as exc:
        logger.error("Failed to load Wikipedia dataset: %s", exc)
        logger.warning("Wikipedia retrieval will be unavailable this session.")

    wiki_ready.set()


# ── public search ─────────────────────────────────────────────────────────────

def bm25_search(query: str, top_k: int = 10) -> list[dict]:
    """BM25 search over Wikipedia articles.

    Returns list of dicts with keys: title, text, score, source_type.
    """
    if _bm25 is None or not _corpus:
        return []

    tokens = query.lower().split()
    scores = _bm25.get_scores(tokens)
    top_idx = sorted(range(len(scores)), key=lambda i: scores[i], reverse=True)[:top_k]

    return [
        {
            "title": _corpus[i]["title"],
            "text": _corpus[i]["text"],
            "score": float(scores[i]),
            "source_type": "wikipedia",
            "source_url": None,
        }
        for i in top_idx
        if scores[i] > 0.0
    ]
