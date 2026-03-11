"""Standalone Wikipedia index preloader.

Run once before starting the server (or bake into a Docker layer):

    uv run python -m knowledge.preload

Downloads the Simple English Wikipedia XML dump (if not already cached),
parses it, builds a BM25 index, and writes .cache/wiki_bm25.pkl.

Subsequent server startups load from the pickle in seconds.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger(__name__)


def main() -> None:
    # Import config from inside ninefrogs/ — add cwd to path if needed
    sys.path.insert(0, str(Path(__file__).parent.parent))

    from config import settings
    from knowledge.wikipedia import _download_dump, _parse_dump

    cache_dir = Path(settings.wiki_cache_dir)
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_file = cache_dir / "wiki_bm25.pkl"
    dump_file  = cache_dir / "simplewiki-latest.xml.bz2"

    if cache_file.exists():
        logger.info("Index already exists at %s — nothing to do.", cache_file)
        logger.info("Delete it and re-run to rebuild.")
        return

    if not dump_file.exists():
        logger.info("Dump not found — downloading…")
        _download_dump(settings.wiki_dump_url, dump_file)
    else:
        logger.info("Dump already downloaded at %s", dump_file)

    logger.info("Building index (this takes ~2 minutes)…")
    bm25, corpus = _parse_dump(dump_file, settings.wiki_max_articles)

    import pickle
    with open(cache_file, "wb") as f:
        pickle.dump((bm25, corpus), f)

    logger.info("Done. Index cached to %s (%s articles).", cache_file, f"{len(corpus):,}")


if __name__ == "__main__":
    main()
