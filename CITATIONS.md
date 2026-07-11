# Nine Frogs — Citations & References

The academic and technical work that informs Nine Frogs' design. Grouped by the part of the system each
underpins. Dates are publication years; web/tool sources note the access date.

*Compiled July 2026. The code-graph / retrieval-SOTA entries reflect the literature review done for the
[repo-native roadmap](ROADMAP.md); recent arXiv IDs are as surfaced in that July 2026 review.*

---

## 1. Learning science & curriculum design (the spiral syllabus + card pedagogy)

- **Ebbinghaus, H. (1885).** *Über das Gedächtnis (Memory: A Contribution to Experimental Psychology).* —
  the forgetting curve; the empirical basis for spacing.
- **Bruner, J. S. (1960).** *The Process of Education.* Harvard University Press. — the **spiral curriculum**.
- **Sweller, J. (1988).** Cognitive load during problem solving: effects on learning. *Cognitive Science*,
  12(2), 257–285. — **cognitive load theory**; worked examples.
- **Bjork, R. A. (1994).** Memory and metamemory considerations in the training of human beings. In
  Metcalfe & Shimamura (Eds.), *Metacognition*. MIT Press. — **desirable difficulties**.
  (See also **Bjork & Bjork, 2011**, "Making things hard on yourself, but in a good way.")
- **Roediger, H. L., & Karpicke, J. D. (2006).** Test-enhanced learning. *Psychological Science*, 17(3),
  249–255. — the **testing effect** / retrieval practice.
- **Kalyuga, S. (2007).** Expertise reversal effect and its implications for learner-tailored instruction.
  *Educational Psychology Review*, 19(4), 509–539. — why instruction must adapt to expertise (drives the
  9-level depth calibration).
- **Vygotsky, L. S. (1978).** *Mind in Society.* Harvard University Press. — the **Zone of Proximal
  Development**; scaffolding.
- **Hattie, J. (2009).** *Visible Learning.* Routledge. — effect sizes (scaffolding, spaced practice).
- **Taylor, K., & Rohrer, D. (2010).** The effects of interleaved practice. *Applied Cognitive Psychology*,
  24(6), 837–848. — **interleaving**.
- **Dunlosky, J., et al. (2013).** Improving students' learning with effective learning techniques.
  *Psychological Science in the Public Interest*, 14(1), 4–58. — ranks spacing & retrieval practice highest.
- **Cambridge Assessment (2020).** *Perspectives on curriculum design: comparing the spiral and the network
  models.* — spiral (dependency-ordered domains) vs network (lateral) — the basis for pairing vertical
  spiral depth with horizontal graph links.

## 2. Spaced-repetition scheduling (the SM-2 engine in `lab/sm2.py`)

- **Leitner, S. (1972).** *So lernt man lernen.* — the Leitner box; interval-based review.
- **Woźniak, P. A. (1990).** *Optimization of learning* (SuperMemo). — the **SM-2 algorithm** Nine Frogs
  uses for both cards and coding challenges.
- **Woźniak, P. A., & Gorzelańczyk, E. J. (1994).** Optimization of repetition spacing in the practice of
  learning. *Acta Neurobiologiae Experimentalis*, 54, 59–62.

## 3. Retrieval & ranking (the hybrid retriever)

- **Page, L., & Brin, S. (1998).** The anatomy of a large-scale hypertextual web search engine. *WWW7*. —
  **PageRank**; the ranking applied to the code-symbol graph (Phase 1).
- **Robertson, S., & Zaragoza, H. (2009).** The Probabilistic Relevance Framework: BM25 and Beyond.
  *Foundations and Trends in IR*, 3(4). — **BM25** (`rank-bm25`).
- **Cormack, G. V., Clarke, C. L. A., & Büttcher, S. (2009).** Reciprocal Rank Fusion outperforms Condorcet
  and individual rank learning methods. *SIGIR '09*. — **RRF**, used to fuse BM25 + vector hits.
- **Xiao, S., et al. (2023).** C-Pack: Packed Resources for General Chinese Embeddings. arXiv:2309.07597. —
  **BGE** embeddings (`bge-base-en-v1.5`, the current default embedder).

## 4. Code understanding & repository-level graphs (Phase 1 — repo-native)

- **Gauthier, P. (2023, Oct 22).** *Building a better repository map with tree-sitter.* aider.chat.
  https://aider.chat/2023/10/22/repomap.html — tree-sitter `def`/`ref` tags → symbol graph → **PageRank**
  → token-budgeted context. The reference implementation for "PageRanked graph of named code objects."
  *(accessed Jul 2026)*
- **tree-sitter** — Brunsfeld, M., et al. An incremental parsing system for programming tools.
  https://tree-sitter.github.io — the AST/def-ref extraction layer.
- **RepoGraph: Enhancing AI Software Engineering with Repository-level Code Graph (2024).**
  arXiv:2410.14684; ICLR 2025. https://arxiv.org/html/2410.14684v1 — repo-level code graph boosts SWE-bench
  agents by ~32.8% relative; validates graph-grounding over flat retrieval.
- **Code Graph Model (CGM): A Graph-Integrated LLM for Repository-Level Software Engineering Tasks (2025).**
  OpenReview. https://openreview.net/forum?id=b98ODdeYq5 — 43% SWE-bench Lite (open Qwen2.5-72B) via a
  graph-RAG framework.
- **Codebase-Memory: Tree-Sitter-Based Knowledge Graphs for LLM Code Exploration via MCP (2026).**
  arXiv:2603.27277. https://arxiv.org/html/2603.27277v1 — local-first, tree-sitter code KGs served over MCP.

## 5. Code embeddings (planned upgrade over the general-purpose default)

- **Qwen3-Embedding (2025/2026).** Qwen team. — ~80.7 MTEB-Code; strongest open code-retrieval option.
- **voyage-code-3 (Voyage AI, 2024/2025).** — commercial code embeddings; ~10% over general-purpose baselines.
- **nomic-embed-code / CodeSage** — open code-specialised embedders.
  *(Nine Frogs currently embeds everything with the general-purpose BGE above; a code model is a Phase-1
  option — see ROADMAP.)*

## 6. Ecosystem / prior art (why the combination is novel)

- **Greptile**, **DeepWiki** — semantic code graphs → Q&A / architecture maps (stop short of a course).
- **CodeGraph**, **GitNexus** — local-first code knowledge graphs over MCP (2026).
- **codebase-to-course** (zarazhangrui) — one-shot read-only HTML course for non-technical users; no SRS,
  labs, or graph. https://github.com/zarazhangrui/codebase-to-course *(accessed Jul 2026)*
- **learning-opportunities** (DrCatHicks) — ephemeral per-change practice exercises; no persistent course.

> None combine graph-grounded understanding + spiral pedagogy + persistent SM-2 decks + runnable verified
> labs + fundamentals cross-links. See [VISION.md](VISION.md).
