# Nine Frogs — Vision

> Point Nine Frogs at a **real codebase** and get back a complete, grounded way to learn it:
> a spiral syllabus, spaced-repetition flashcard decks, and runnable lab exercises — teaching both
> *this* codebase and the transferable skills underneath it, cross-linked to foundational courses.

Today Nine Frogs turns a **topic** into a spiral syllabus → Anki cards, plus a LeetCode-style **Labs**
system (see [README](README.md)). The next chapter makes a **repository** a first-class input.

> ### The one-line positioning
> **Nobody combines graph-grounded understanding + spiral pedagogy + persistent SM-2 decks + runnable
> verified labs + fundamentals cross-links.**
>
> Each piece exists somewhere; the *combination* — grounded, persistent, **practised**, and pedagogically
> structured — does not. That is what Nine Frogs is.

## What "repo-native" means

Ingest a repo and generate, grounded in the code that's actually there:

1. **A syllabus** whose structure tracks the repo's real architecture (endpoints → async chains → data
   layer → cloud integration → testing), not a generic topic outline.
2. **Flashcard decks** — a **mega deck** for the whole repo plus **per-subject decks**, including
   project-specific cards: *how does this repo handle auth? the database layer? the AWS setup?*
3. **Lab exercises** — the codebase's own important pieces become challenges you re-implement from
   scratch (a model registry, overrideable settings, a docker-run with overrides, Bayesian-opt vs a
   baseline, a seasonal time-series model), test-verified with `pytest`, scheduled with SM-2, run through
   campaign/practice mode. External services (boto3, Langfuse, ClearML) are **mocked**, with commentary on
   how.
4. **Cross-links to compiled foundational courses** — the ML/backend material links down to the maths,
   chemistry, physics, and tech-stack courses it rests on. Links resolve to `linked` (course exists) or
   `proposed` (a signal for which foundational course to author next).

### Two worked examples

- **A 142-endpoint FastAPI / Celery / async / AWS server** → a course on that stack, with exercises that
  implement the full request→task→analytics chains, mocking commentary for the AWS/observability calls,
  and decks showing how *that* project does auth, databases, and its AWS wiring.
- **biopoly** (the ML formulation repo) → chemistry / physics / ML cross-links, with labs for the model
  registry, overrideable `BaseSettings`, docker overrides, Bayesian-opt vs baseline, seasonal time-series,
  external APIs, and ClearML.

## How it works — four layers

1. **Code understanding.** Parse the repo with **tree-sitter** into definitions and references of named
   objects (functions, classes, methods), build a dependency graph, and rank importance with **PageRank**
   (`networkx`). Embed each symbol with a code-specific model. This yields *degrees of certainty and
   links*: PageRank = centrality, edges = dependencies, embedding similarity = lateral relationships.
2. **Course generation.** The PageRank-ranked "spine" of the repo plus its detected tech stack drive
   syllabus synthesis, so the course follows the code's real backbone.
3. **Decks.** Cards generated per syllabus section and per high-centrality symbol, routed into an Anki
   deck hierarchy (`Repo::Subject`).
4. **Labs.** The most central symbols become runnable exercises, verified by hidden `pytest` suites in
   isolated runners, scheduled by SM-2 and sequenced by campaigns.

### Cross-cutting: lightweight usage analytics

A **non-critical, fail-open** analytics layer records *how the system is used* — so the tool can show you
your own learning (streaks, cards/day, lab pass-rate per subject, time-on-task, which subjects are
neglected) and so the pedagogy can be tuned against real behaviour. Principles:

- **Fail-open:** a `record_event(...)` helper swallows all errors — analytics can never break a study
  session, a card review, or a lab run.
- **Small surface:** one append-only `UsageEvent` table (`ts`, `event_type`, `subject?`, `entity_id?`,
  `duration_ms?`, small JSON `payload`). Events like `card_reviewed`, `lab_started/passed/failed`,
  `syllabus_generated`, `repo_ingested`, `deck_pushed`.
- **Reuses what exists:** lab telemetry is already captured (`CodingAttempt.time_spent_seconds`/`status`,
  `ChallengeProgress` SM-2 state and `total_attempts`/`total_passes`, `Campaign.total_time_seconds`); this
  layer unifies it and adds the flashcard/study/generation events, surfaced on a simple `/analytics` view.
- **Local & private:** it's a personal tool — no PII beyond local usage, no external telemetry.

## Why this is worth building (and not already done)

The technique is proven — a PageRanked tree-sitter symbol graph is how **Aider's repo map** selects
context, and graph-grounded code understanding is a live research frontier (RepoGraph, Code Graph Models)
and product space (Greptile, DeepWiki, local-first code-KG tools). But those stop at **Q&A and
architecture maps**. The "codebase → course" tools that exist are thin: one-shot read-only HTML for
non-technical users, or ephemeral per-change exercises.

**Nobody combines graph-grounded understanding + a spiral-pedagogy syllabus + persistent SM-2 flashcard
decks + runnable, test-verified labs + fundamentals cross-links.** That combination — grounded, persistent,
*practised*, and pedagogically structured — is what Nine Frogs is for. The full landscape review and design
detail live in the roadmap.

See **[ROADMAP.md](ROADMAP.md)** for the phased plan and current status, and **[CITATIONS.md](CITATIONS.md)**
for the dated academic and technical work behind the design.
