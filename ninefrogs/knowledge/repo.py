"""Repository ingestion — walk a code repo and ingest it into a collection.

Mirrors ``knowledge.crawler`` / ``ingest_crawl`` but the source is a local
directory tree instead of a website.  Each selected file becomes one Document
via :func:`knowledge.ingest.ingest_text` (source_type="repo"), so all the
downstream machinery — chunking, SHA dedup, embedding, collection-scoped vector
search — is reused unchanged.

Extraction strategy per file:
  - Markdown / config / text  → full text.
  - Python                    → full source if small (≤ ``full_source_max_bytes``),
                                otherwise an *API digest* (module docstring +
                                class/function signatures & their docstrings)
                                built with ``ast`` — keeps chunks meaningful
                                rather than drowning retrieval in boilerplate.

Public API
----------
ingest_repo(db, collection_id, repo_path, *, full_source_max_bytes=8000)
    → list[Document]   (the documents actually created, dedup-skipped omitted)

CLI
---
python -m knowledge.repo <path> --collection <name>
    Create-if-absent a collection by name and ingest the repo into it.
"""
from __future__ import annotations

import ast
import uuid
from pathlib import Path
from typing import Iterable

from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Document, DocumentCollection
from knowledge.ingest import ingest_text


# ── file selection ─────────────────────────────────────────────────────────────

# Directories never walked into.
_SKIP_DIRS = {
    ".git", ".venv", "venv", "env", "__pycache__", ".pytest_cache",
    ".ruff_cache", ".mypy_cache", "node_modules", ".cache", ".idea", ".vscode",
    "mlruns", "artifacts", "figures", "data", "site-packages", "dist", "build",
    ".ipynb_checkpoints",
}

# Extensions read as full plain text.
_TEXT_EXTS = {
    ".md", ".rst", ".txt", ".toml", ".yml", ".yaml", ".cfg", ".ini",
    ".env-example", ".example",
}

# Filenames (no useful extension) read as full plain text.
_TEXT_NAMES = {
    "Dockerfile", "docker-compose.yml", "Makefile", "CONTRIBUTING",
    ".pre-commit-config.yaml", ".gitignore", ".dockerignore",
}

# Never ingest these (data / binaries / lockfiles).
_SKIP_EXTS = {
    ".lock", ".db", ".sqlite", ".parquet", ".csv", ".npy", ".npz", ".pkl",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".pdf",
    ".zip", ".gz", ".bz2", ".tar", ".whl", ".so", ".pyc", ".pyd", ".bin",
    ".onnx", ".pt", ".pth", ".safetensors",
}
_SKIP_FILENAMES = {"uv.lock", "poetry.lock", "package-lock.json", "yarn.lock"}


def _should_skip_dir(name: str) -> bool:
    return name in _SKIP_DIRS or name.startswith(".") and name not in {".github"}


def _iter_files(repo_path: Path) -> Iterable[Path]:
    """Yield ingestible files under repo_path, pruning skip-dirs."""
    for path in sorted(repo_path.rglob("*")):
        if path.is_dir():
            continue
        # Prune if any parent dir is a skip-dir
        if any(_should_skip_dir(part) for part in path.relative_to(repo_path).parts[:-1]):
            continue
        if path.name in _SKIP_FILENAMES or path.suffix.lower() in _SKIP_EXTS:
            continue
        yield path


# ── extraction ─────────────────────────────────────────────────────────────────

def _signature(node: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Render a def line without evaluating annotations/defaults deeply."""
    try:
        args = ast.unparse(node.args)
    except Exception:
        args = "..."
    prefix = "async def" if isinstance(node, ast.AsyncFunctionDef) else "def"
    ret = ""
    if node.returns is not None:
        try:
            ret = f" -> {ast.unparse(node.returns)}"
        except Exception:
            ret = ""
    return f"{prefix} {node.name}({args}){ret}"


def _python_digest(source: str, rel_path: str) -> str:
    """Module docstring + class/function signatures & docstrings via ast."""
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        logger.warning("Cannot parse %s (%s) — ingesting raw", rel_path, exc)
        return source

    parts: list[str] = [f"# Module: {rel_path}"]
    mod_doc = ast.get_docstring(tree)
    if mod_doc:
        parts.append(mod_doc.strip())

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            parts.append(_signature(node))
            doc = ast.get_docstring(node)
            if doc:
                parts.append("    " + doc.strip().replace("\n", "\n    "))
        elif isinstance(node, ast.ClassDef):
            parts.append(f"class {node.name}:")
            cls_doc = ast.get_docstring(node)
            if cls_doc:
                parts.append("    " + cls_doc.strip().replace("\n", "\n    "))
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    parts.append("    " + _signature(sub))
                    doc = ast.get_docstring(sub)
                    if doc:
                        parts.append("        " + doc.strip().replace("\n", "\n        "))

    return "\n\n".join(parts)


def _extract(path: Path, rel_path: str, full_source_max_bytes: int) -> str | None:
    """Return the text to ingest for one file, or None to skip."""
    try:
        raw = path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        logger.debug("Skipping non-utf8/unreadable file: %s", rel_path)
        return None

    if not raw.strip():
        return None

    suffix = path.suffix.lower()
    if suffix == ".py":
        # Small files are fully informative and cheap — keep full source.
        if len(raw.encode("utf-8")) <= full_source_max_bytes:
            return f"# File: {rel_path}\n\n{raw}"
        return _python_digest(raw, rel_path)

    if suffix in _TEXT_EXTS or path.name in _TEXT_NAMES or suffix == "":
        return raw

    return None


# ── ingestion ──────────────────────────────────────────────────────────────────

async def ingest_repo(
    db: AsyncSession,
    collection_id: uuid.UUID,
    repo_path: str | Path,
    *,
    full_source_max_bytes: int = 8000,
) -> list[Document]:
    """Walk a repository and ingest each selected file as a Document."""
    repo_path = Path(repo_path).resolve()
    if not repo_path.is_dir():
        raise NotADirectoryError(f"Not a directory: {repo_path}")

    docs: list[Document] = []
    seen = 0
    for path in _iter_files(repo_path):
        rel_path = path.relative_to(repo_path).as_posix()
        text = _extract(path, rel_path, full_source_max_bytes)
        if text is None:
            continue
        seen += 1
        doc = await ingest_text(
            db=db,
            collection_id=collection_id,
            title=rel_path,
            source_type="repo",
            raw_text=text,
            source_uri=str(path),
        )
        if doc:
            docs.append(doc)

    logger.info(
        "Repo ingest complete: %s → %d documents (%d files considered)",
        repo_path.name, len(docs), seen,
    )
    return docs


async def get_or_create_collection(
    db: AsyncSession, name: str, description: str | None = None
) -> DocumentCollection:
    """Fetch a collection by name, creating it if absent."""
    existing = await db.scalar(
        select(DocumentCollection).where(DocumentCollection.name == name)
    )
    if existing:
        return existing
    collection = DocumentCollection(name=name.strip(), description=description)
    db.add(collection)
    await db.commit()
    await db.refresh(collection)
    return collection


# ── CLI ────────────────────────────────────────────────────────────────────────

async def _run(repo_path: str, collection_name: str) -> None:
    from db.engine import async_session_factory
    import db.models  # noqa: F401 — populate metadata

    async with async_session_factory() as db:
        collection = await get_or_create_collection(
            db, collection_name, description=f"Repository: {Path(repo_path).name}"
        )
        docs = await ingest_repo(db, collection.id, repo_path)

    print(f"\nIngested {len(docs)} documents into collection '{collection_name}' ({collection.id}).")


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Ingest a code repository into a Nine Frogs collection")
    parser.add_argument("repo_path", help="Path to the repository root")
    parser.add_argument(
        "--collection", "-c", required=True,
        help="Collection name (created if it does not exist)",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.repo_path, args.collection))


if __name__ == "__main__":
    main()
