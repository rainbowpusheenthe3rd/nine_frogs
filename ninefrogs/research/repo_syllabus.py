"""Repo → drills-style syllabus generation.

Reads a repository that has been ingested into a document collection (see
``knowledge.repo``) and synthesises a **constructivist spiral** course *for that
repo*, following the Nine Frogs pedagogy: each level's depth increase is
triggered by a failure of the previous level's mental model.

The output is a ``RepoSyllabus`` that serialises straight to
``drills/syllabuses/<subject>.yaml`` — a first-class subject the existing loader
and drills→cards bridge already consume. It is written as a **reviewable draft**
(edit before trusting), matching Nine Frogs' accept/edit philosophy everywhere.

Fundamentals cross-linking: the prompt is given a catalog of the syllabuses that
already exist, and asked to name the science-fundamentals each level rests on.
Links to existing syllabuses resolve to ``linked``; named-but-absent fundamentals
(e.g. ``chemistry`` for biopoly) resolve to ``proposed`` — the backlog of what to
author next.

Override (bypass the local LLM)
-------------------------------
Local 7B/12B models are currently too weak for this nested, grounded generation
task (qwen2.5:7b hallucinated a generic "Git" course from the biopoly repo). Until
a stronger syllabus model is wired (see the nine_frogs ROADMAP), set

    NINEFROGS_SYLLABUS_OVERRIDE=<path-to-authored.yaml>

on the run and the tool loads that authored ``RepoSyllabus`` and **skips the LLM
entirely** — everything downstream (status resolution, write) is unchanged.

CLI
---
python -m research.repo_syllabus --collection biopoly --subject biopoly
NINEFROGS_SYLLABUS_OVERRIDE=.../authored/biopoly.yaml \
    python -m research.repo_syllabus --collection biopoly --subject biopoly
"""
from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import yaml
from loguru import logger
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Document, DocumentChunk, DocumentCollection
from lab.subjects import fundamentals_catalog, load_all_syllabuses
from llm.client import get_syllabus_llm_client
from llm.schemas import RepoSyllabus

SYLLABUSES_DIR = Path(__file__).parent.parent.parent.parent / "Organiser" / "drills" / "syllabuses"

_CONTEXT_BUDGET = 14_000  # chars of repo context fed to the model
_OVERRIDE_ENV = "NINEFROGS_SYLLABUS_OVERRIDE"


def load_override_syllabus(subject: str) -> RepoSyllabus | None:
    """If ``NINEFROGS_SYLLABUS_OVERRIDE`` is set, load an authored syllabus from that
    path and skip the local LLM entirely. Returns None when the env var is unset.
    """
    path = os.environ.get(_OVERRIDE_ENV)
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"{_OVERRIDE_ENV}={path!r} but no such file exists")
    data = yaml.safe_load(p.read_text(encoding="utf-8"))
    syllabus = RepoSyllabus.model_validate(data)
    syllabus.subject = subject
    logger.info("Using authored syllabus override (local LLM skipped): %s", p)
    return syllabus


# ── context assembly ───────────────────────────────────────────────────────────

def _doc_priority(title: str) -> int:
    """Lower sorts first. High-signal narrative docs before code."""
    t = title.lower()
    if "readme" in t:
        return 0
    if any(k in t for k in ("talk_track", "data_card", "results", "contributing")):
        return 1
    if t.endswith(".md"):
        return 2
    if t.endswith((".toml", ".yml", ".yaml", "dockerfile")):
        return 4
    return 3  # code


async def _gather_context(db: AsyncSession, collection_id: uuid.UUID) -> str:
    """Concatenate the collection's documents (narrative first) up to a budget."""
    doc_rows = await db.execute(
        select(Document).where(Document.collection_id == collection_id)
    )
    docs = sorted(doc_rows.scalars().all(), key=lambda d: (_doc_priority(d.title), d.title))

    parts: list[str] = []
    total = 0
    for doc in docs:
        chunk_rows = await db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.position)
        )
        body = "\n".join(c.content for c in chunk_rows.scalars().all())
        entry = f"===== {doc.title} =====\n{body}"
        if total + len(entry) > _CONTEXT_BUDGET:
            entry = entry[: max(0, _CONTEXT_BUDGET - total)]
            if entry:
                parts.append(entry)
            break
        parts.append(entry)
        total += len(entry)
    return "\n\n".join(parts)


# ── prompt ─────────────────────────────────────────────────────────────────────

_SYSTEM = (
    "You are an expert curriculum designer building a constructivist SPIRAL "
    "course from a real code repository. Each level's depth increase must be "
    "triggered by a concrete failure of the previous level's mental model — not "
    "generic 'intro/intermediate/advanced' padding. Levels progress from the "
    "simplest working idea to research-level depth. Return only JSON."
)


def _user_prompt(repo_context: str, catalog: list[dict], subject: str) -> str:
    catalog_str = json.dumps(catalog, indent=1)
    return (
        f"Repository content (narrative docs first, then code):\n{repo_context}\n\n"
        f"Existing fundamentals syllabuses you can cross-link to (as prerequisites):\n"
        f"{catalog_str}\n\n"
        "Design a spiral syllabus FOR THIS REPOSITORY.\n"
        f"- subject slug: '{subject}'.\n"
        "- 5-7 levels. Each level: a specific title, a 'mode' (cards|mixed|exercises), "
        "a 1-2 sentence description, 4-10 concrete `concepts`, 2-4 `objectives` "
        "(each starting 'Learner will be able to…'), and the `prerequisites` "
        "(science-fundamentals) that level rests on.\n"
        "- prerequisites: prefer linking to an existing syllabus by its exact `subject` "
        "slug from the catalog above (name the relevant `levels`). You MAY also name a "
        "fundamentals subject that is NOT in the catalog yet (e.g. 'chemistry', "
        "'physics', 'materials_science') if the material genuinely rests on it — it "
        "will be recorded as a proposed prerequisite. Every prerequisite needs a one-line "
        "`why`. Do not set `status`.\n"
        "- Also give 3-6 subject-wide `prerequisites`, a `domain` (e.g. 'ml'), a `type`, "
        "a `description`, and `sources` (the repo's own key docs are fine).\n"
        "Make the spiral honest to what the code actually does."
    )


# ── generation ─────────────────────────────────────────────────────────────────

async def generate_repo_syllabus(
    db: AsyncSession, collection_name: str, subject: str
) -> RepoSyllabus:
    collection = await db.scalar(
        select(DocumentCollection).where(DocumentCollection.name == collection_name)
    )
    if not collection:
        raise ValueError(f"Collection '{collection_name}' not found — ingest the repo first.")

    context = await _gather_context(db, collection.id)
    if not context.strip():
        raise ValueError(f"Collection '{collection_name}' has no ingested content.")

    catalog = fundamentals_catalog(load_all_syllabuses())
    llm = get_syllabus_llm_client()

    logger.info("Generating repo syllabus for '%s' (%d chars context)…", subject, len(context))
    syllabus: RepoSyllabus = await llm.complete_json(
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": _user_prompt(context, catalog, subject)},
        ],
        schema=RepoSyllabus,
        temperature=0.2,
    )
    # Force the slug we were asked for (models sometimes rename it)
    syllabus.subject = subject
    return syllabus


def resolve_and_dump(syllabus: RepoSyllabus) -> str:
    """Resolve prerequisite statuses against existing syllabuses and return YAML."""
    known = set(load_all_syllabuses().keys())
    data = syllabus.model_dump()

    def _mark(pres: list) -> None:
        for pre in pres or []:
            pre["status"] = "linked" if pre.get("subject") in known else "proposed"

    _mark(data.get("prerequisites", []))
    for lvl in data.get("levels", []):
        _mark(lvl.get("prerequisites", []))

    return yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False)


async def _run(collection_name: str, subject: str, out_path: str | None) -> None:
    from db.engine import async_session_factory
    import db.models  # noqa: F401

    # Escape hatch: an authored syllabus bypasses the local LLM entirely.
    syllabus = load_override_syllabus(subject)
    if syllabus is None:
        async with async_session_factory() as db:
            syllabus = await generate_repo_syllabus(db, collection_name, subject)

    yaml_text = resolve_and_dump(syllabus)
    out = Path(out_path) if out_path else (SYLLABUSES_DIR / f"{subject}.yaml")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml_text, encoding="utf-8")

    proposed = [
        p["subject"]
        for lvl in syllabus.model_dump()["levels"]
        for p in (lvl.get("prerequisites") or [])
        if p.get("subject") not in load_all_syllabuses()
    ]
    print(f"\nWrote draft syllabus → {out}")
    print(f"  {len(syllabus.levels)} levels.")
    if proposed:
        print(f"  Proposed (not-yet-authored) fundamentals: {sorted(set(proposed))}")
    print("  Review/edit before it goes live in the drills picker.")


def main() -> None:
    import argparse
    import asyncio

    parser = argparse.ArgumentParser(description="Generate a drills syllabus from an ingested repo")
    parser.add_argument("--collection", "-c", required=True, help="Ingested collection name")
    parser.add_argument("--subject", "-s", required=True, help="Syllabus subject slug (e.g. biopoly)")
    parser.add_argument("--out", "-o", default=None, help="Output path (default: drills/syllabuses/<subject>.yaml)")
    args = parser.parse_args()
    asyncio.run(_run(args.collection, args.subject, args.out))


if __name__ == "__main__":
    main()
