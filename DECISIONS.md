# Nine Frogs — Architecture Decisions

A short log of the load-bearing decisions, so future work (and future readers) know *why* things are
shaped the way they are. See [VISION.md](VISION.md) for the goal, [ROADMAP.md](ROADMAP.md) for what's next.

## Decisions (11 Jul 2026 session)

**D1 — Repo ingestion is flat chunk-and-embed (for now).** Reuse the source-agnostic
`knowledge/ingest.py::ingest_text` (chunk → SHA-dedup → embed → pgvector) rather than anything code-aware.
*Why:* fastest path to a working collection; the code-graph layer supersedes it later. *Status:* **shipped**
(biopoly = 37 docs / 41 chunks). *Caveat:* this is the naïve baseline the SOTA code-graph layer (Phase 1)
is meant to replace — **no code/dependency graph exists yet.**

**D2 — A repo "course" is a drills-style YAML (`RepoSyllabus`), not a new DB model.** It serialises to
`drills/syllabuses/<subject>.yaml`, a drop-in for the existing `lab/subjects.py` loader and the
`web/routes/drills.py` → cards bridge. *Why:* the hybrid output (first-class subject **and** flashcards)
comes almost for free. *Status:* **shipped.**

**D3 — Fundamentals cross-linking via `prerequisites` with resolved status.** Each prereq is
`{subject, levels, why, status}`; `status` is computed at load — `linked` if that syllabus exists, else
`proposed`. *Why:* `proposed` links are the "author this next" backlog (later: rank by in-degree/PageRank).
*Status:* **shipped.**

**D4 — Labs are hand-seeded from real repo modules, with self-contained tests.** Tests use an inline
`importlib` loader (no `conftest`) so they run in the isolated `lab/runner.py::run_pytest_challenge` temp
dir. An LLM lab-generator is deferred and will sit behind a human-review gate. *Why:* trustworthy tests
first; the existing drills tests actually *don't* run in the isolated runner (they depend on a conftest).
*Status:* **shipped** (3 biopoly labs, imported).

**D5 — Syllabus/card generation needs a stronger model than local 7B; ship an override.** qwen2.5:7b
hallucinated a generic *"Git"* course on the nested, grounded `RepoSyllabus` task. Decision:
`NINEFROGS_SYLLABUS_OVERRIDE=<authored.yaml>` bypasses the LLM entirely (author the syllabus, load it).
*Why:* unblocks the demo without a naff LLM in the loop. *Status:* **shipped** — biopoly syllabus authored
by Claude. *Revisit:* route generation to Claude via `SYLLABUS_LLM_*`, and/or decompose the one-shot
nested-JSON prompt into per-level calls. **Card generation still runs on qwen2.5:7b — same revisit.**

**D6 — Keep `bge-base` as the default embedder; a code model is a Phase-1 option.** *Why:* avoid a second
model load / API dependency until the code-graph work needs it. *Status:* decided, **unbuilt** (candidates:
Qwen3-Embedding, voyage-code-3, nomic-embed-code).

**D7 — Code graph will be symbol-level, not line-level.** Functions/classes/methods as nodes (Aider-style
tree-sitter `def`/`ref` + PageRank), over RepoGraph's line-level graph. *Why:* matches "named objects,"
proven, simpler. *Status:* decided, **unbuilt** (Phase 1).

**D8 — Analytics is lightweight, non-critical, fail-open.** A `record_event()` that swallows all errors,
an append-only `UsageEvent` table, reusing existing lab telemetry (`CodingAttempt`/`ChallengeProgress`/
`Campaign`). *Why:* usage insight must never break a study/lab session. *Status:* designed, **unbuilt**.

**D9 — Public biopoly repo history was rebuilt safely; never rewrite either repo again.** Rebuilt the
public `biopoly-formulation-ml` from its *already-anonymised* content (final tree byte-identical to the old
squash — verified before push), anon author identity, real dates, no Claude co-author trailers. *Why:* show
the employer clean conventional-commit devops without touching content or leaking identity. *Status:*
**shipped.** *Rule going forward:* only ADD conventional commits to either biopoly repo — no force-push /
history rewrite.
