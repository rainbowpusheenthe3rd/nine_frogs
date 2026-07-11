# Nine Frogs

> AI-powered spaced-repetition **and** coding-lab system for engineers with a maths/science bent:
> deep research → spiral syllabus → targeted Anki cards, plus a LeetCode-style **Labs** environment
> for a real ML / backend tech stack.

## What it does (v1)

Nine Frogs has two halves that share one syllabus model.

### 1. Syllabus → Flashcards → Anki
- Give it a **topic**, or point it at an ingested **document collection** or **code repository**.
- **Deep research:** the LLM generates search queries; retrieval runs over the collection's
  embeddings in **pgvector**, fused with Reciprocal Rank Fusion.
- It synthesises a **spiral syllabus** (see the pedagogy below); you **accept / edit / reject** each section.
- It generates questions per section, then candidate **flashcards** (BM25 + semantic retrieval,
  reranked); you review each card.
- Accepted cards **push to Anki** via AnkiConnect.

### 2. Nine Frog Labs — coding challenges
LeetCode-style, but for a real stack: write code that passes hidden `pytest` suites, timed, in
isolated runners (subprocess pytest, or an ephemeral **Docker** container for service/app challenges).
- Challenges come from hand-authored YAML (`drills/exercises/<subject>/lN_*.yaml` + `drills/tests/`)
  and public datasets (MBPP, HumanEval+, NeetCode / LeetCode).
- **SM-2 spaced repetition** on challenges; **campaigns** run you through a subject's levels;
  every attempt is stored for progress and report cards.

Current lab coverage (target is 9 levels per subject):

| Subject | Syllabus | Exercises |
|---|---|---|
| FastAPI | ✓ | L2–L6 |
| Celery | ✓ | L2–L5 |
| git | ✓ | L2–L4 |
| PyTorch | — | L2–L4 |
| RAG | ✓ | L2–L5 |
| DSA | ✓ | NeetCode / LeetCode datasets |
| biopoly (repo-generated) | draft | L3–L5 |
| Async, Docker | — | — *(planned)* |

### Repo → course (new)
Point the ingester at a repository and it becomes a knowledge collection, then a course:

```bash
python -m knowledge.repo <path-to-repo> -c <name>        # ingest repo → pgvector collection
python -m research.repo_syllabus -c <name> -s <subject>  # → drills/syllabuses/<subject>.yaml (draft)
```

The generated syllabus **cross-links to science-fundamentals syllabuses** (maths / chemistry /
physics): each prerequisite resolves to `linked` when that syllabus exists, or `proposed` (an
"author this next" signal) when it doesn't. Its ML sections seed programming labs.

### Not in v1 (deliberately out of scope)
The vision paragraph under *Curriculum Design Philosophy* below describes the full intended system.
Two parts are **not** wired in v1:
- **Wikipedia-slimline ingestion** ("the entirety of Wikipedia into a network graph") — retrieval
  runs over your **own ingested collections / repos** instead.
- **Web crawler** — the code exists (`knowledge/crawler.py`, the `/collections/{id}/ingest/crawl`
  route) but is not part of the v1 flow.

## Where this is going

The next chapter makes a **repository** a first-class input: ingest a real codebase and generate a
grounded syllabus, flashcard decks, and runnable labs over a PageRanked code graph.

> **Nobody combines graph-grounded understanding + spiral pedagogy + persistent SM-2 decks + runnable
> verified labs + fundamentals cross-links.** That combination is what Nine Frogs is for.

See **[VISION.md](VISION.md)**, the phased **[ROADMAP.md](ROADMAP.md)**, and the dated
**[CITATIONS.md](CITATIONS.md)**.

## Running on Windows

A single PowerShell script starts everything: Redis (Docker), Ollama, the Celery worker, and the app.

```powershell
# From the repo root
.\start.ps1
```

**What it does by default:**
1. Checks `uv` and `docker` are on PATH
2. Copies `.env.example` → `.env` if missing (edit it before continuing)
3. Starts Redis via Docker (`redis:7-alpine` on port 6379)
4. Checks Ollama on `:11434`, starts it if it isn't running
5. Runs `uv sync`
6. Opens the Celery worker in a new PowerShell window
7. Starts the FastAPI app in the foreground — **http://localhost:8080**

**Flags:**
```powershell
.\start.ps1 -SkipOllama   # using Anthropic or OpenAI instead of a local model
.\start.ps1 -SkipRedis    # Redis is already running externally
.\start.ps1 -SkipWorker   # don't need the Labs task queue
```

First run downloads Wikipedia Simple (~500 MB) and builds a BM25 index (~2 min). Both are cached to `.cache/` and reused on subsequent starts.

---

## Quick Start (manual)

**Prerequisites:** PostgreSQL + pgvector, `uv`, Ollama (or an Anthropic/OpenAI API key), Anki + AnkiConnect, Redis.

```bash
# 1. Install dependencies
cd ninefrogs
uv sync

# 2. Configure environment
cp .env.example .env
# Edit .env: set DATABASE_URL, choose LLM_PROVIDER

# 3. Create the database
psql -c "CREATE DATABASE ninefrogs;"
psql -d ninefrogs -c "CREATE EXTENSION IF NOT EXISTS vector;"

# 4. Start Redis
docker run -d --name redis -p 6379:6379 redis:7-alpine

# 5. Start the Celery worker (separate terminal)
cd ninefrogs
uv run celery -A lab.tasks.celery_app worker --loglevel=info --pool=solo

# 6. Run the app
uv run python main.py
```

App is available at **http://localhost:8080**.

---

## LLM Options

### Default: Ollama (local)

```bash
ollama pull qwen2.5:7b
uv run python main.py
```

### Claude (Anthropic) — terminal override

No `.env` edits required. Environment variables take precedence over `.env`.

**PowerShell:**

```powershell
$env:LLM_PROVIDER="anthropic"
$env:LLM_MODEL="claude-sonnet-4-6"
$env:LLM_API_KEY="sk-ant-..."
uv run python main.py
```

**cmd.exe:**

```cmd
set LLM_PROVIDER=anthropic && set LLM_MODEL=claude-sonnet-4-6 && set LLM_API_KEY=sk-ant-... && uv run python main.py
```

To route only the syllabus step through Claude (keeping Ollama for everything else):

```powershell
$env:SYLLABUS_LLM_PROVIDER="anthropic"
$env:SYLLABUS_LLM_MODEL="claude-opus-4-6"
$env:SYLLABUS_LLM_API_KEY="sk-ant-..."
uv run python main.py
```

### OpenAI

```powershell
$env:LLM_PROVIDER="openai"
$env:LLM_MODEL="gpt-4o-mini"
$env:LLM_BASE_URL="https://api.openai.com/v1"
$env:LLM_API_KEY="sk-..."
uv run python main.py
```

---

## Persistent Cache

The PostgreSQL database holds all sessions, embeddings, approved cards, and Labs progress — back it up with standard `pg_dump`. (A Wikipedia BM25 cache under `ninefrogs/.cache/` is used only if the out-of-scope Wikipedia path is enabled; it is not needed for v1.)

---

# Nine Frogs — Curriculum Design Philosophy

> *Deep research, generates a candidate syllabus. A human reviews it: accept / edit / reject. A web crawler harvests content. The entirety of Wikipedia-slimline is ingested into a network graph. Embeddings are stored in a vector DB. The LLM generates questions relating to each part of the syllabus in a structured fashion. The LLM generates candidate flashcards using cross-direction reranker against BM25 + semantic distance retrieval. Human-in-the-loop review for candidate cards. Accepted cards go into a deck. Push to Anki via AnkiConnect API.*

> **v1 status:** this paragraph is the *full* vision. The **web crawler** and **Wikipedia-slimline network graph** steps are not wired in v1 (see *Not in v1* at the top) — retrieval runs over your own ingested collections/repos. Everything else — syllabus generation, human review, question and flashcard generation, and the Anki push — is implemented, alongside the Nine Frog Labs system.

This document is the pedagogical foundation for how Nine Frogs designs, generates, and structures syllabi. It is both a philosophy document and — eventually — the basis of the instruction set passed to the LLM when generating curricula.

---

## The Problem with Traditional Approaches

There are two obvious ways to structure a curriculum for a technical subject. Both are wrong in isolation.

### Bottom-Up: Sheet Music Without the Song

The bottom-up approach starts with foundations and builds upward. To learn Git, you first study SHA-1 hashing and content-addressable storage. To learn Linux, you first study the kernel's process table. To learn music, you first study the circle of fifths.

The appeal is obvious: nothing is introduced before its prerequisite. The dependency graph is respected. Everything is logically grounded.

The failure is equally obvious: **the learner has no idea why they are learning any of this.** The object model of Git is fascinating — if you already know what a merge conflict is, if you've already been burned by a detached HEAD, if you've already wondered what "rewriting history" means. Without that experiential context, it is just abstract data structure taxonomy.

Pedagogical research calls this *inert knowledge*: information that has been encoded but cannot be retrieved or applied because it was never connected to a real problem. The learner can describe a commit object but cannot diagnose a broken repository.

### Top-Down: Vibing with the Guitar

The top-down approach starts with the end goal and works backwards. To learn Git, you clone a repository, make a commit, push it to GitHub, and open a pull request — on day one. To learn music, you pick up the guitar and play along to a song you love.

The appeal here is also obvious: immediate wins, real context, visible progress. The learner is doing the thing, not studying the thing.

The failure is equally predictable: **the mental model stays shallow.** When something breaks — a merge conflict, a rebased branch, a missing dependency — the learner has no conceptual tools to diagnose it. They have patterns, not understanding. They can drive the car but cannot open the bonnet.

Pedagogical research calls this *fragile knowledge*: behaviour that works in familiar contexts but fails to transfer. The learner can follow the steps but cannot adapt when the steps don't apply.

### The False Choice

The instinct is to split the difference — some theory, some practice, interleaved somewhat arbitrarily. This produces a curriculum that is neither well-grounded nor well-motivated. It is the worst of both worlds: abstract enough to bore beginners, shallow enough to frustrate advanced learners.

The research points to a third structure. Not a compromise. A genuinely different shape.

---

## The Research Foundation

### Cognitive Load Theory (Sweller, 1988)

Human working memory is severely limited. Learning fails not because information is absent but because too much of it competes for attention simultaneously. Sweller's Cognitive Load Theory identifies three types of load:

- **Intrinsic load**: the inherent complexity of the material
- **Extraneous load**: complexity introduced by poor instructional design
- **Germane load**: the productive effort of building new schemas

The practical implication: novices need *worked examples* that reduce extraneous load and let them focus on schema-building. Experts need *problem-solving* that challenges and extends existing schemas.

This leads directly to the **expertise reversal effect** (Kalyuga, 2007): the same instruction that helps beginners actively harms experts. A curriculum that works for a novice is wrong for an intermediate learner. A curriculum that works for an intermediate is wrong for a novice. Instructional design must be *adaptive* to expertise, not fixed.

Empirically: low prior knowledge learners benefit from high-assistance instruction (effect size d = +0.505). High prior knowledge learners benefit from low-assistance instruction (d = −0.428). The reversal is not a marginal finding — it is robust across a wide variety of domains.

### Vygotsky's Zone of Proximal Development (1934)

Vygotsky defined the ZPD as "the distance between the actual developmental level as determined by independent problem solving and the level of potential development as determined through problem-solving under adult guidance, or in collaboration with more capable peers."

In practice: learning happens at the edge of current capability. Below the ZPD, the learner is bored. Above it, the learner is overwhelmed. Instruction that stays in the ZPD — challenging but achievable — is where development occurs.

*Scaffolding* — the temporary support structure that enables a learner to operate within their ZPD — has an effect size of **0.82** in Hattie's Visible Learning database, placing it in the top 10 of 252 measured educational interventions. The critical word is *temporary*: scaffolding that is not removed as expertise grows becomes a crutch that impedes development rather than enabling it.

The implication for curriculum design: structure must adjust dynamically. The right level of support for Pass 1 is the wrong level of support for Pass 5.

### Bruner's Spiral Curriculum (1960)

Jerome Bruner proposed that "any subject can be taught effectively in some intellectually honest form to any child at any stage of development" — provided the curriculum returns to the same material repeatedly at increasing levels of sophistication.

The spiral curriculum has three core principles:

1. **Revisit**: students return to the same ideas, concepts, and subjects repeatedly over the course of their learning
2. **Build**: each revisit adds depth and complexity, not just repetition
3. **Connect**: each revisit makes explicit the connection to previous encounters with the material

Research on the specific features of spiral curricula is strong:
- Spaced practice: effect size **0.71**, rated highest utility of any learning strategy reviewed (Dunlosky et al., 2013)
- Interleaved practice: **43% improvement** on delayed tests versus blocked practice (Taylor & Rohrer, 2010)
- The spacing gap itself creates retrieval difficulty — what Bjork calls a *desirable difficulty*

### Desirable Difficulties (Bjork, 1994)

Robert Bjork coined the term *desirable difficulties* for conditions that slow apparent learning but dramatically improve long-term retention and transfer. The core four are:

1. **Spacing**: distributing practice over time rather than massing it
2. **Interleaving**: mixing topics rather than blocking them by category
3. **Retrieval practice**: testing rather than re-studying
4. **Generation**: attempting to produce an answer before being shown it

These feel worse to learners in the moment — they are harder, slower, more effortful. But the difficulty is the mechanism: *making retrieval hard makes retention durable.* A curriculum that feels smooth and easy is often a curriculum that produces knowledge with a short half-life.

The spiral curriculum, properly implemented, incorporates all four. The gap between passes introduces spacing. Revisiting a concept in a new context introduces interleaving. The "model breaks" moment — encountering a problem the current understanding cannot solve — is a generation event: the learner must attempt to explain or solve something before the answer is provided.

### Network vs. Spiral: A Note on Knowledge Structure

Cambridge Assessment research (2020) makes the useful observation that the spiral model fits well-structured knowledge domains (mathematics, computer science, physics) where there is genuine dependency ordering — you cannot fully understand concept B without concept A.

For less-structured domains (humanities, arts, qualitative disciplines), a *network* model — where concepts connect laterally in many directions rather than vertically in increasing depth — may be more appropriate.

Nine Frogs operates primarily in technical domains with strong dependency structures. The spiral is the right shape here. But the retrieval system (BM25 + vector cross-direction search) naturally surfaces lateral connections — concepts that are related but not prerequisite. The curriculum should make use of both: vertical depth (spiral) and horizontal connection (network).

---

## The Framework: Constructivist Spiral with Just-in-Time Depth

Synthesising the above, the framework Nine Frogs uses — and that should be instilled in syllabus generation — is:

> **A constructivist spiral curriculum where each increase in depth is triggered by a real problem the learner has experienced, scaffolding is removed as expertise develops, and concepts are revisited with spaced, interleaved retrieval practice.**

In structural terms:

```
Pass N+1 is unlocked by a specific failure mode of Pass N's mental model.
```

Each pass has four components:

1. **The trigger** — a real, concrete problem that the current mental model cannot solve. This is what motivates the new layer.
2. **The new layer** — the concept, mechanism, or mental model that resolves the trigger and deepens understanding.
3. **The recontextualisation** — an explicit callback: "what you learned in Pass N was always this, you just didn't need to see it yet."
4. **The forecast** — a hint at where the current model will next break, creating anticipation rather than closure.

This structure is not linear. It is a helix: the learner passes over the same conceptual territory multiple times, but from higher altitude each time. What looked like a timeline of saves is revealed to be a commit graph. What looked like a commit graph is revealed to be a directed acyclic graph of content-addressed objects. The final understanding subsumes all previous ones rather than replacing them.

---

## Examples

### Git: From Timeline to Object Store

**Pass 1 mental model:** Git saves snapshots of your project over time.

This is not wrong. It is *incomplete*. It is the right level of complexity for a learner who needs to start committing and pushing code. It breaks predictably when they try to work on two things at once.

**Pass 2 trigger:** "I want to fix a bug without touching my new feature."

This cannot be solved with the Pass 1 model. The learner needs branches — parallel timelines. They will experience a merge conflict before this pass is over. That conflict is not a failure; it is the designed trigger for the next layer.

**Pass 5 trigger:** "Why is HEAD detached? What does 'not a commit' mean?"

These are unexplainable within the branch-and-timeline model. They require the object model: refs as files containing SHA-1 hashes, HEAD as a symbolic ref, commits as objects with parent pointers. But notice that this arrives at Pass 5, not Pass 1. The learner has context. They have experienced the thing that this explanation resolves. The object model is not introduced as a prerequisite — it is introduced as an explanation.

**Recontextualisation at Pass 5:** "Every command you've ever run was just reading and writing objects and moving ref pointers. `git add` writes a blob. `git commit` writes a tree and a commit. `git branch` writes a file."

The learner's entire prior experience is suddenly re-illuminated. Nothing they learned was wrong. It was always this. They just didn't need to see it yet.

**Pass 7:** Implement it from scratch. Write `git init`, `git hash-object`, `git commit-tree`. The learner who has been through all seven passes can do this because they have encountered every concept at the moment it was needed, in the context that made it meaningful.

---

### Linux: From Commands to Kernel

**Pass 1 mental model:** Linux is a computer you control with text commands.

Correct. Incomplete. Breaks when the learner tries to run a script and gets "Permission denied."

**Pass 2 trigger:** Permission denied.

The learner needs users, groups, chmod, the execute bit. But they are not learning this from a textbook chapter on file permissions. They are learning it because their script won't run. The motivation is intrinsic.

**Pass 6 trigger:** "Why is this process using 100% CPU? What is a file descriptor? Why does everything seem to be a file?"

These questions cannot be answered by anything in Passes 1–5. They require the kernel boundary: system calls, `/proc`, file descriptors as universal handles, virtual memory. But the learner has been using all of these without knowing it. `cat file.txt` was calling `open()`, `read()`, `write()`, `close()`. The pipe in `ls | grep foo` was two file descriptors pointing at the same kernel buffer. Pass 6 makes this visible.

**Pass 8:** Write a shell from scratch using `fork()`, `exec()`, `wait()`. Write a minimal init that can start processes, reap zombies, and forward signals. The learner has spent eight passes using these abstractions. Now they build them.

---

## Strengths of the Spiral Approach

**Motivation is persistent and intrinsic.** Each depth increase is triggered by a real problem. The learner wants the answer before they receive it. This is the opposite of "we're covering this because it's on the curriculum."

**Knowledge is transferable.** Spaced and interleaved revisiting builds flexible schemas rather than rote memory. The learner has encountered the concept in multiple contexts at increasing depth. It can be retrieved and applied in novel situations.

**Adaptive to expertise.** The expertise reversal effect is naturally accommodated. Early passes use heavy scaffolding (worked examples, guided progression). Later passes remove scaffolding and require problem-solving. The curriculum does not assume a fixed level of support.

**Mental models grow without being invalidated.** Pass 1's "timeline of saves" is still true at Pass 7. It is merely incomplete. Learners do not experience the disorientation of "everything I knew was wrong" — they experience expansion, not replacement.

**Multiple stopping points.** A learner who needs only Pass 3 for their job can stop. A learner who wants Pass 7 has a path. One curriculum structure serves multiple legitimate endpoints.

**Recontextualisation creates "aha" moments.** The explicit callback at each pass — "this is what that always was" — produces the characteristic insight experience that learners remember and that drives further engagement.

---

## Weaknesses and Failure Modes

**Fragmentation without explicit connection.** The research notes "fragmented skill-concept development" as a common failure mode in poorly implemented spirals. If the revisit does not explicitly callback to prior learning, the learner may not connect the new depth to the existing schema. The recontextualisation step is not optional — it is the mechanism.

**Requires expert curriculum design.** Bottom-up is easy to design: topological sort of the concept dependency graph. Top-down is easy: list the use cases. The spiral requires knowing both — and, critically, knowing where the learner's current model will predictably break. This is tacit expert knowledge about the learning journey, not just knowledge of the subject. For an LLM-generated syllabus, this is the hardest thing to get right.

**Pacing divergence.** Learners hit "break" moments at different rates. In self-directed learning contexts (flashcards, tutorials, personal projects), this is manageable — the learner proceeds when they have experienced the trigger. In synchronised group contexts (classrooms, cohorts), spiral curricula create synchronisation problems.

**No single empirical verdict on the whole system.** ERIC's meta-review found "no clear empirical evidence of the overall effects of the spiral curriculum on student learning." The features — spaced practice, interleaving, retrieval practice — have strong individual evidence. The integrated system is harder to study cleanly. This is not a reason to abandon the approach; the mechanistic evidence for each component is robust. But it should prevent overclaiming.

**Surface repetition without depth.** A poorly implemented spiral just repeats the same content at the same depth with different examples. The learner correctly identifies this as redundant and disengages. Each revisit must genuinely add a layer — the re-exposure is only valuable if the altitude has increased.

**Assessment mismatch.** Traditional assessment (end-of-chapter test, move on) does not fit a spiral structure. The learner's understanding of Pass 1 material at Pass 5 is richer than at Pass 1, but a Pass 1 test cannot capture this. Assessment should probe depth across passes — asking not "what is a commit" but "why does `git rebase` create new commits rather than moving existing ones."

---

## Implications for Nine Frogs

### Syllabus Generation

When the LLM generates a syllabus, it should not produce a flat list of topics ordered by dependency or by use-case frequency. It should produce a set of *passes* — each with:

- A **current mental model** (what the learner believes at this stage)
- A **trigger** (the specific failure mode that motivates the next pass)
- A **new layer** (what concept resolves the trigger)
- A **recontextualisation** (what earlier knowledge is reilluminated)
- A **next break forecast** (where the new model will predictably fail)

The number of passes should reflect the subject's depth. A subject with a shallow knowledge structure (how to use a specific API, how to configure a tool) may require only 3–4 passes. A subject with deep dependency structures (operating systems, compilers, cryptography) may require 7–8.

### Flashcard Generation

Flashcards should be generated with awareness of which pass they belong to. A card generated at Pass 2 should not require Pass 5 knowledge to answer correctly. A card generated at Pass 5 can and should build on Pass 2 understanding.

Cross-direction retrieval is particularly valuable here: a card about a Pass 5 concept can retrieve Pass 2 examples from the knowledge base, grounding the abstract in something the learner has already encountered. This is the mechanistic implementation of the recontextualisation step.

The spacing algorithm (Anki's SM-2 or similar) handles the temporal dimension of the spiral automatically: cards are reviewed at increasing intervals, creating the spaced retrieval that underpins long-term retention. The syllabus structure handles the depth dimension. Together, they implement both axes of the spiral.

### Depth Calibration

The system should be capable of generating syllabi at different depth targets. A user studying Git for a job as a frontend developer needs Passes 1–3. A user studying Git to contribute to Gitoxide needs Passes 1–7. The depth target should be specified at the start and should inform which triggers, breaks, and recontextualisations are included.

This maps to the educational level framing:

| Pass Range | Equivalent Level | Outcome |
|---|---|---|
| 1 | GCSE | Functional use in familiar contexts |
| 2–3 | A-Level / College | Independent use, handles common failures |
| 3–4 | Undergraduate | Collaborative work, reasoned tradeoffs |
| 5 | MSc | Mechanistic understanding, can explain behaviour |
| 6 | PhD | Deep internals, can reason about edge cases |
| 7+ | Postdoc / Researcher | Can implement, extend, or critique the system |

---

## The Instruction Set

This document is the source of truth for the pedagogical philosophy. From it, two artifacts will be derived:

1. **The raw instruction set**: a condensed, precise set of instructions passed to the LLM when generating a syllabus. These instructions specify the pass structure, required fields, trigger logic, and recontextualisation requirement.

2. **The philosophy document** (this file): the full reasoning, evidence base, and examples that inform anyone working on the curriculum generation system — human or LLM — who needs to understand *why* the instructions are what they are.

The separation matters. An instruction set optimised for LLM consumption will be terse, structured, and explicit about format. A philosophy document optimised for human understanding will be discursive, example-rich, and source-cited. Both are necessary. Neither substitutes for the other.

---

## Sources and Further Reading

> The full, dated reference list — pedagogy, spaced-repetition, retrieval/ranking, and the code-graph SOTA
> behind the [roadmap](ROADMAP.md) — lives in **[CITATIONS.md](CITATIONS.md)**. A selection follows.

- Sweller, J. (1988). Cognitive load during problem solving: Effects on learning. *Cognitive Science*, 12(2), 257–285.
- Kalyuga, S. (2007). Expertise reversal effect and its implications for learner-tailored instruction. *Educational Psychology Review*, 19(4), 509–539.
- Vygotsky, L. S. (1978). *Mind in Society: The Development of Higher Psychological Processes*. Harvard University Press.
- Bruner, J. S. (1960). *The Process of Education*. Harvard University Press.
- Bjork, R. A. (1994). Memory and metamemory considerations in the training of human beings. In J. Metcalfe & A. Shimamura (Eds.), *Metacognition: Knowing about knowing* (pp. 185–205). MIT Press.
- Dunlosky, J., Rawson, K. A., Marsh, E. J., Nathan, M. J., & Willingham, D. T. (2013). Improving students' learning with effective learning techniques. *Psychological Science in the Public Interest*, 14(1), 4–58.
- Taylor, K., & Rohrer, D. (2010). The effects of interleaved practice. *Applied Cognitive Psychology*, 24(6), 837–848.
- Hattie, J. (2009). *Visible Learning: A Synthesis of Over 800 Meta-Analyses Relating to Achievement*. Routledge.
- Cambridge Assessment (2020). [Perspectives on curriculum design: comparing the spiral and the network models](https://www.cambridgeassessment.org.uk/Images/598388-perspectives-on-curriculum-design-comparing-the-spiral-and-the-network-models.pdf).
- [Cognitive Load Theory in Computing Education Research — ACM TOCE](https://dl.acm.org/doi/full/10.1145/3483843)
- [Worked-example effect — Wikipedia](https://en.wikipedia.org/wiki/Worked-example_effect)
- [Spiral Curriculum — InnerDrive](https://www.innerdrive.co.uk/blog/the-spiral-curriculum/)
- [Desirable Difficulties — Bjork Lab UCLA](https://bjorklab.psych.ucla.edu/wp-content/uploads/sites/13/2016/04/EBjork_RBjork_2011.pdf)
