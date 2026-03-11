"""Domain-scoped web crawler with boilerplate removal.

- Stays within the origin domain of the seed URL.
- Follows links ordered by depth (BFS-style).
- Sliding-window token-overlap algorithm strips repeated boilerplate
  (nav, cookie banners, footers that repeat across pages).
- Text extraction via BeautifulSoup with lxml backend.
"""
from __future__ import annotations

from loguru import logger
import re
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup

from config import settings


_STRIP_TAGS = ["nav", "footer", "script", "style", "header", "aside", "form", "noscript"]
_UA = "NineFrogs/1.0 (educational research tool)"


# ── helpers ───────────────────────────────────────────────────────────────────

def _domain(url: str) -> str:
    return urlparse(url).netloc


def _extract_links(html: str, base_url: str, domain: str) -> list[str]:
    soup = BeautifulSoup(html, "lxml")
    links: list[str] = []
    for tag in soup.find_all("a", href=True):
        full = urljoin(base_url, tag["href"]).split("#")[0].split("?")[0]
        parsed = urlparse(full)
        if parsed.netloc == domain and parsed.scheme in ("http", "https"):
            links.append(full)
    return list(dict.fromkeys(links))  # dedupe preserving order


def _sliding_window_clean(text: str, window: int = 150, threshold: float = 0.55) -> str:
    """Remove repeated boilerplate paragraphs using sliding-window overlap."""
    words = text.split()
    if len(words) < window:
        return text

    seen: list[frozenset] = []
    clean: list[str] = []
    step = window // 2

    for i in range(0, len(words), step):
        chunk = words[i : i + window]
        chunk_set = frozenset(chunk)
        if not any(
            len(chunk_set & prev) / max(len(chunk_set | prev), 1) > threshold
            for prev in seen
        ):
            clean.extend(chunk[:step])
            seen.append(chunk_set)
            if len(seen) > 30:
                seen.pop(0)

    return " ".join(clean)


def _extract_text(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(_STRIP_TAGS):
        tag.decompose()
    raw = soup.get_text(separator=" ", strip=True)
    raw = re.sub(r"\s+", " ", raw).strip()
    return _sliding_window_clean(raw)


# ── public API ────────────────────────────────────────────────────────────────

async def crawl(seed_url: str, max_pages: int | None = None) -> list[dict]:
    """Crawl seed_url within its domain.

    Returns list of dicts: {url, title, text, source_type="web"}.
    """
    max_pages = max_pages or settings.crawl_max_pages
    domain = _domain(seed_url)
    queue: list[tuple[str, int]] = [(seed_url, 0)]
    visited: set[str] = set()
    pages: list[dict] = []

    async with httpx.AsyncClient(
        timeout=settings.crawl_timeout,
        follow_redirects=True,
        headers={"User-Agent": _UA},
    ) as client:
        while queue and len(pages) < max_pages:
            url, depth = queue.pop(0)
            if url in visited:
                continue
            visited.add(url)

            try:
                resp = await client.get(url)
                ct = resp.headers.get("content-type", "")
                if "text/html" not in ct:
                    continue

                html = resp.text
                text = _extract_text(html)
                soup = BeautifulSoup(html, "lxml")
                title = (soup.title.string.strip() if soup.title else url) or url

                pages.append(
                    {"url": url, "title": title, "text": text[:5000], "source_type": "web"}
                )
                logger.debug("Crawled [%d] %s", depth, url)

                if depth < 3:
                    for link in _extract_links(html, url, domain):
                        if link not in visited:
                            queue.append((link, depth + 1))

            except Exception as exc:
                logger.warning("Failed to crawl %s: %s", url, exc)

    logger.info("Crawl complete: %d pages from %s", len(pages), seed_url)
    return pages
