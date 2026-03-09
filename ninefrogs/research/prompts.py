"""Prompt templates for the research and flashcard pipelines.

Prompts are tuned for 7B instruction-tuned models (e.g. qwen2.5:7b):
  - Short system prompts (≤ 100 tokens)
  - Explicit output format stated literally
  - temperature=0.1-0.2 for structured outputs, 0.6-0.7 for generative
"""
from __future__ import annotations

# ── Research: query generation ────────────────────────────────────────────────

QUERY_GEN_SYSTEM = (
    "You are a research assistant. Generate diverse search queries to gather "
    "comprehensive information about a topic. Return only JSON."
)


def query_gen_user(topic: str, previous_queries: list[str], iteration: int) -> str:
    avoid = ""
    if previous_queries:
        listed = "\n".join(f"- {q}" for q in previous_queries)
        avoid = f"\n\nAlready searched (do NOT repeat):\n{listed}"

    extra = ""
    if iteration > 0:
        extra = "\nFocus on gaps: advanced concepts, applications, history, misconceptions."

    return (
        f"Topic: {topic}{avoid}{extra}\n\n"
        "Generate 5 diverse, specific search queries that will find useful information.\n"
        'Return JSON: {"queries": ["query 1", "query 2", "query 3", "query 4", "query 5"]}'
    )


# ── Research: syllabus synthesis ──────────────────────────────────────────────

SYLLABUS_SYSTEM = (
    "You are an expert curriculum designer. Create structured, progressive learning "
    "syllabi. Sections must be specific — not generic placeholders. Return only JSON."
)


def syllabus_user(topic: str, context: str) -> str:
    return (
        f"Topic: {topic}\n\n"
        f"Source material:\n{context}\n\n"
        "Create a learning syllabus with 5-7 sections. "
        "Sections must progress from foundational to advanced. "
        "Each section should be specific enough to generate targeted flashcards.\n\n"
        "Return JSON:\n"
        "{\n"
        '  "title": "Full topic title",\n'
        '  "overview": "2-3 sentence learning path description",\n'
        '  "sections": [\n'
        "    {\n"
        '      "title": "Specific section title",\n'
        '      "summary": "2-3 sentences describing what this section covers",\n'
        '      "learning_objectives": ["Learner will be able to...", "..."],\n'
        '      "key_concepts": ["concept1", "concept2", "concept3"]\n'
        "    }\n"
        "  ]\n"
        "}"
    )


# ── Flashcards: question generation ──────────────────────────────────────────

SECTION_QUERY_SYSTEM = (
    "You are an expert educator. Generate specific, testable questions to assess "
    "mastery of a syllabus section. Questions must be concrete, not generic. "
    "Return only JSON."
)


def section_query_user(
    title: str, summary: str, objectives: list[str], concepts: list[str]
) -> str:
    obj_str = "\n".join(f"  - {o}" for o in objectives)
    concept_str = ", ".join(concepts)
    return (
        f"Section: {title}\n"
        f"Summary: {summary}\n"
        f"Learning objectives:\n{obj_str}\n"
        f"Key concepts: {concept_str}\n\n"
        "Generate 6-8 specific questions that test mastery of this section.\n"
        "Include: definitions, applications, comparisons, processes.\n"
        "Each question must be specific to this section — not applicable to any topic.\n\n"
        'Return JSON: {"questions": ["question 1", "question 2", ...]}'
    )


# ── Flashcards: card generation ───────────────────────────────────────────────

FLASHCARD_SYSTEM = (
    "You are an Anki flashcard expert. Create precise, atomic cards: one fact per card. "
    "Answers must be 1-3 sentences, accurate to the source material. Return only JSON."
)


def flashcard_user(section_title: str, question: str, context_chunks: list[str]) -> str:
    ctx = "\n\n".join(f"[{i + 1}] {chunk[:600]}" for i, chunk in enumerate(context_chunks[:4]))
    return (
        f"Section: {section_title}\n"
        f"Question: {question}\n\n"
        f"Source material:\n{ctx}\n\n"
        "Create 1-2 Anki flashcards for this question.\n"
        "Rules:\n"
        "  - front: specific question (not generic)\n"
        "  - back: concise answer (1-3 sentences), grounded in source material\n"
        "  - hint: optional mnemonic or context clue (or null)\n"
        "  - tags: 2-4 lowercase kebab-case tags\n\n"
        'Return JSON: {"cards": [{"front": "...", "back": "...", "hint": null, "tags": ["..."]}]}'
    )
