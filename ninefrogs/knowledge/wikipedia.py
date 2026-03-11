"""Wikipedia knowledge source.

Downloads the Simple English Wikipedia XML dump directly from Wikimedia's
official dump server, parses it locally, strips wiki markup, builds a BM25
index, and pickles the result to WIKI_CACHE_DIR.

First run: ~500 MB download + ~2 min to build index.
Subsequent runs: loads from cache in seconds.

`wiki_ready` is an asyncio.Event set when the index is ready — callers
`await wiki_ready.wait()` before issuing queries.
"""
from __future__ import annotations

import asyncio
import bz2
from loguru import logger
import pickle
import re
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import networkx as nx

from config import settings


# Dedicated single-thread executor — Wikipedia loading never blocks the
# default executor used by hybrid_search, embeddings, etc.
_wiki_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="wiki")

# ── module-level singletons ───────────────────────────────────────────────────
_bm25 = None
_corpus: list[dict] = []       # [{title, text, idx}]
_graph: nx.Graph = nx.Graph()
wiki_ready = asyncio.Event()

# ── observable loading state (polled by /wiki/ready) ─────────────────────────
wiki_state: dict = {
    "status": "idle",       # idle | downloading | parsing | indexing | ready | error
    "pct": 0,               # 0-100
    "articles": 0,
    "message": "Not started",
}

# MediaWiki XML namespace
_MW_NS = "http://www.mediawiki.org/xml/export-0.11/"


# ── wiki markup stripping ─────────────────────────────────────────────────────

def _strip_markup(text: str) -> str:
    """Strip the most common MediaWiki markup to get plain text."""
    # Remove templates {{ ... }}
    while "{{" in text:
        text = re.sub(r"\{\{[^{}]*\}\}", "", text)
    # Remove [[File:...]] / [[Image:...]] blocks
    text = re.sub(r"\[\[(?:File|Image):[^\]]*\]\]", "", text, flags=re.IGNORECASE)
    # Convert [[link|label]] → label, [[link]] → link
    text = re.sub(r"\[\[(?:[^|\]]*\|)?([^\]]+)\]\]", r"\1", text)
    # Remove external links [http... label] → label
    text = re.sub(r"\[https?://\S+\s+([^\]]+)\]", r"\1", text)
    text = re.sub(r"\[https?://\S+\]", "", text)
    # Remove HTML tags
    text = re.sub(r"<[^>]+>", "", text)
    # Remove bold/italic markers
    text = re.sub(r"'{2,3}", "", text)
    # Remove section headers === ... ===
    text = re.sub(r"={2,6}[^=\n]+={2,6}", "", text)
    # Collapse whitespace
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text.strip()


# ── XML dump parser ───────────────────────────────────────────────────────────

def _parse_dump(dump_path: Path, max_articles: int) -> tuple:
    """Parse a bz2-compressed MediaWiki XML dump and build a BM25 index.

    Returns (bm25, corpus) where corpus is a list of dicts.
    """
    from rank_bm25 import BM25Okapi

    corpus: list[dict] = []
    tokenized: list[list[str]] = []

    title_tag = f"{{{_MW_NS}}}title"
    text_tag  = f"{{{_MW_NS}}}text"
    ns_tag    = f"{{{_MW_NS}}}ns"
    page_tag  = f"{{{_MW_NS}}}page"

    logger.info("Parsing Wikipedia dump %s …", dump_path)
    wiki_state["status"] = "parsing"
    wiki_state["pct"] = 0
    wiki_state["message"] = "Parsing Wikipedia dump…"

    with bz2.open(dump_path, "rb") as fh:
        context = ET.iterparse(fh, events=("end",))
        title = text = ns = None

        for _event, elem in context:
            tag = elem.tag

            if tag == title_tag:
                title = (elem.text or "").strip()
            elif tag == ns_tag:
                ns = elem.text or "0"
            elif tag == text_tag:
                text = (elem.text or "")[:4000]
            elif tag == page_tag:
                # Only keep main namespace (ns=0), skip redirects
                if ns == "0" and title and text and not text.startswith("#REDIRECT"):
                    clean = _strip_markup(text)[:2000]
                    combined = f"{title} {clean}"
                    tokenized.append(combined.lower().split())
                    corpus.append({"title": title, "text": clean, "idx": len(corpus)})

                    if len(corpus) % 10_000 == 0:
                        pct = min(90, len(corpus) * 90 // max_articles)
                        wiki_state["pct"] = pct
                        wiki_state["articles"] = len(corpus)
                        wiki_state["message"] = f"Parsing articles… {len(corpus):,} / {max_articles:,}"
                        logger.info("  Parsed %d articles…", len(corpus))
                    if len(corpus) >= max_articles:
                        break

                # Free memory
                elem.clear()
                title = text = ns = None

    logger.info("Building BM25 index over %s articles…", f"{len(corpus):,}")
    wiki_state["status"] = "indexing"
    wiki_state["pct"] = 92
    wiki_state["message"] = f"Building BM25 index over {len(corpus):,} articles…"
    bm25 = BM25Okapi(tokenized)
    return bm25, corpus


# ── dump downloader ───────────────────────────────────────────────────────────

def _download_dump(url: str, dest: Path) -> None:
    """Stream-download the dump file with progress logging."""
    import urllib.request

    logger.info("Downloading Wikipedia dump from %s …", url)
    logger.info("This is a ~500 MB file — please wait…")
    wiki_state["status"] = "downloading"
    wiki_state["message"] = "Downloading Wikipedia dump (~500 MB)…"

    def _report(block_num: int, block_size: int, total_size: int) -> None:
        if total_size > 0 and block_num % 500 == 0:
            pct = min(100, block_num * block_size * 100 // total_size)
            wiki_state["pct"] = pct
            wiki_state["message"] = f"Downloading Wikipedia dump… {pct}%"
            logger.info("  Download progress: %d%%", pct)

    urllib.request.urlretrieve(url, dest, reporthook=_report)
    wiki_state["pct"] = 100
    logger.info("Download complete: %s", dest)


# ── public async loader ───────────────────────────────────────────────────────

async def load_wikipedia() -> None:
    """Download / parse the Wikipedia dump and build a BM25 index.

    Safe to call at startup as an asyncio task.
    """
    global _bm25, _corpus

    if not settings.wiki_enabled:
        logger.info("Wikipedia disabled (WIKI_ENABLED=false).")
        wiki_state["status"] = "ready"
        wiki_state["pct"] = 100
        wiki_state["message"] = "Wikipedia disabled."
        wiki_ready.set()
        return

    cache_dir = Path(settings.wiki_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "wiki_bm25.pkl"
    dump_file  = cache_dir / "simplewiki-latest.xml.bz2"

    loop = asyncio.get_event_loop()

    # ── 1. try pickle cache ───────────────────────────────────────────────────
    if cache_file.exists():
        logger.info("Loading Wikipedia index from cache…")
        wiki_state["status"] = "parsing"
        wiki_state["pct"] = 95
        wiki_state["message"] = "Loading index from cache…"
        try:
            _bm25, _corpus = await loop.run_in_executor(
                _wiki_executor,
                lambda: pickle.load(open(cache_file, "rb")),  # noqa: SIM115
            )
            logger.info("Loaded %s Wikipedia articles from cache.", f"{len(_corpus):,}")
            wiki_state["status"] = "ready"
            wiki_state["pct"] = 100
            wiki_state["articles"] = len(_corpus)
            wiki_state["message"] = f"Ready — {len(_corpus):,} articles indexed."
            wiki_ready.set()
            return
        except Exception as exc:
            logger.warning("Cache load failed (%s) — rebuilding.", exc)
            wiki_state["message"] = f"Cache corrupt — rebuilding… ({exc})"

    # ── 2. download dump if not present ──────────────────────────────────────
    if not dump_file.exists():
        try:
            await loop.run_in_executor(
                _wiki_executor,
                lambda: _download_dump(settings.wiki_dump_url, dump_file),
            )
        except Exception as exc:
            logger.error("Failed to download Wikipedia dump: %s", exc)
            logger.warning("Wikipedia retrieval will be unavailable this session.")
            wiki_ready.set()
            return

    # ── 3. parse dump + build index ───────────────────────────────────────────
    try:
        _bm25, _corpus = await loop.run_in_executor(
            _wiki_executor,
            lambda: _parse_dump(dump_file, settings.wiki_max_articles),
        )

        # Persist cache
        wiki_state["status"] = "indexing"
        wiki_state["pct"] = 97
        wiki_state["message"] = "Writing cache…"
        await loop.run_in_executor(
            _wiki_executor,
            lambda: pickle.dump((_bm25, _corpus), open(cache_file, "wb")),  # noqa: SIM115
        )
        logger.info("Wikipedia index cached to %s.", cache_file)
        wiki_state["status"] = "ready"
        wiki_state["pct"] = 100
        wiki_state["articles"] = len(_corpus)
        wiki_state["message"] = f"Ready — {len(_corpus):,} articles indexed."

    except Exception as exc:
        logger.error("Failed to build Wikipedia index: %s", exc)
        logger.warning("Wikipedia retrieval will be unavailable this session.")
        wiki_state["status"] = "error"
        wiki_state["message"] = str(exc)

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
