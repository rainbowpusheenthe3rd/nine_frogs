# Nine Frogs — Roadmap

Toward **repo-native Nine Frogs** (see [VISION.md](VISION.md)): ingest a real codebase → syllabus + decks +
labs, grounded in a PageRanked code graph and cross-linked to foundational courses. Multi-session build.

**Status (July 2026):** Phase 0 shipped. Phase 1 is the next build.

---

## Phase 0 — Repo → syllabus + fundamentals cross-links + seeded labs ✅ *shipped*

- [x] Repo ingester `knowledge/repo.py` (tree walk → ast digest / full source → `ingest_text` → pgvector)
- [x] `RepoSyllabus` schema + `research/repo_syllabus.py` → drills-style syllabus draft
- [x] Fundamentals cross-linking: `prerequisites` resolve to `linked` / `proposed` (`lab/subjects.py`)
- [x] 3 hand-seeded biopoly labs (PSI, register-if-better, distance-to-target) — 20 tests green
- [x] README rewritten: accurate v1 scope (Wikipedia-slimline + web crawler marked out of scope)

## Phase 1 — Code-understanding foundation *(next — primary)*

- [ ] `knowledge/codegraph.py`: tree-sitter (`grep-ast` / `tree-sitter-language-pack`) → `def`/`ref` tags
      → dependency graph → **PageRank** (`networkx`, already a dependency)
- [ ] `CodeSymbol` + `CodeEdge` DB models + Alembic migration; embed symbols with a **code** model
      (config-selectable, bge-base fallback)
- [ ] `/graph` route + template — visualise the ranked graph (the demo artifact)
- [ ] Feed the PageRank-ranked "spine" into `research/repo_syllabus.py`
- **Verify (biopoly):** PageRank top-N are the real core objects (`ModelRegistry`, `Settings`,
  `score_prediction`, `detect_drift`, `ForwardModel`); syllabus spine reflects centrality

> **⚠️ Known issue — syllabus-gen model quality (found on the first live spin, 11 Jul).** Local
> 7B/12B models hallucinate on the nested, grounded `RepoSyllabus` task — qwen2.5:7b produced a
> generic *"Git"* course from the biopoly repo (ungrounded, zero cross-links). **Shipped an escape
> hatch:** `NINEFROGS_SYLLABUS_OVERRIDE=<authored.yaml>` bypasses the LLM and loads a hand-authored
> syllabus (used to produce the live biopoly course from `drills/authored/biopoly.yaml`). **Fix to
> revisit:** route syllabus generation to a stronger model (Claude via `SYLLABUS_LLM_*`), and/or
> decompose the one-shot nested-JSON prompt into per-level calls to make it tractable for local models.

## Phase 2 — Labs from the graph *(primary)*

- [ ] High-centrality symbols → lab specs; add biopoly labs (model registry, overrideable `BaseSettings`,
      docker-run overrides, bayesopt vs baseline, seasonal time-series, ClearML)
- [ ] **External-API mocking** convention (monkeypatch / `moto` / `responses` for boto3/Langfuse/ClearML)
      so tests never hit real services
- [ ] Reuse `lab/importer.py`, `lab/runner.py`, `lab/sm2.py`, campaigns; hand-seed first, LLM generator
      behind a human-review gate

## Phase 3 — Decks (mega + per-subject)

- [ ] Deck routing in the Anki push (`web/routes/anki.py`) → `Repo::Subject` hierarchy
- [ ] Project-specific cards in `flashcards/generator.py`, grounded in each symbol's graph neighborhood
      ("how does *this* repo do auth / DB / AWS")

## Phase 4 — Foundational courses

- [ ] Author/generate the compiled courses the cross-links point at, prioritised by **in-degree of
      `proposed` nodes** (the graph says which to build first: chemistry, physics, async, docker, AWS)
- [ ] Push the CV-stack labs toward **L9**: FastAPI, Celery, **async**, **docker**, PyTorch, git
      (async & docker are greenfield; others reach L2–L6 today)

## Phase 5 — Generalize to any repo

- [ ] The work 142-endpoint FastAPI/Celery/AWS server as the "it generalizes" proof —
      **LOCAL ONLY**, outputs gitignored, never pushed (proprietary; generated content leaks architecture)

## Cross-cutting — lightweight usage analytics *(ships alongside Phase 1)*

- [ ] **Fail-open** `record_event(...)` helper (swallows all errors — never breaks a study/lab session)
- [ ] Append-only `UsageEvent` table (`ts`, `event_type`, `subject?`, `entity_id?`, `duration_ms?`, JSON
      `payload`); events: `card_reviewed`, `lab_started/passed/failed`, `syllabus_generated`,
      `repo_ingested`, `deck_pushed`
- [ ] `/analytics` view (streaks, cards/day, lab pass-rate per subject, time-on-task, neglected subjects)
- [ ] Reuse existing telemetry: `CodingAttempt`, `ChallengeProgress` (SM-2, attempts/passes), `Campaign`
- Local & private (personal tool) — no external telemetry, non-critical by design

---

### SOTA anchors (so we build the good version)

tree-sitter def/ref + PageRank symbol graph ([Aider repo map](https://aider.chat/2023/10/22/repomap.html)) ·
graph-grounded understanding ([RepoGraph, ICLR 2025](https://arxiv.org/html/2410.14684v1);
[Code Graph Models](https://openreview.net/forum?id=b98ODdeYq5)) · code embeddings
(Qwen3-Embedding / voyage-code-3 / nomic-embed-code — current `bge-base` is general-purpose).

Full dated references: **[CITATIONS.md](CITATIONS.md)**.
