"""Shared syllabus and subject loading for drills and lab routes."""
from __future__ import annotations

from pathlib import Path

import yaml

SYLLABUSES_DIR = Path(__file__).parent.parent.parent.parent.parent / "Organiser" / "drills" / "syllabuses"
NEETCODE_YAML = Path(__file__).parent / "neetcode150.yaml"

_DOMAIN_DISPLAY = {
    "algorithms": "Algorithms & Data Structures",
    "web": "Web & APIs",
    "ml": "Machine Learning",
    "mathematics": "Mathematics",
    "cs_foundations": "CS Foundations",
    "tools": "Tools & Workflow",
    "other": "Other",
}


def load_all_syllabuses() -> dict[str, dict]:
    """Load all subject YAML files. Returns {subject_slug: subject_dict}."""
    result: dict[str, dict] = {}
    if not SYLLABUSES_DIR.exists():
        return result
    for f in sorted(SYLLABUSES_DIR.glob("*.yaml")):
        try:
            with open(f, encoding="utf-8") as fh:
                data = yaml.safe_load(fh)
            slug = data["subject"]
            result[slug] = {
                "id": slug,
                "title": data.get("title", slug),
                "type": data.get("type", "mixed"),
                "domain": data.get("domain", "other"),
                "parent": data.get("parent"),
                "description": data.get("description", ""),
                # Subject-wide fundamentals cross-links (resolved later)
                "prerequisites": data.get("prerequisites", []),
                "levels": [
                    {
                        "level": lvl["level"],
                        "title": lvl.get("title", f"Level {lvl['level']}"),
                        "mode": lvl.get("mode", "mixed"),
                        "topic": lvl.get("topic"),
                        "neetcode_patterns": lvl.get("neetcode_patterns", []),
                        # Carried through so the drills→cards bridge has real
                        # concepts/objectives to generate from (previously dropped).
                        "description": lvl.get("description", ""),
                        "concepts": lvl.get("concepts", []),
                        "objectives": lvl.get("objectives", []),
                        "prerequisites": lvl.get("prerequisites", []),
                    }
                    for lvl in data.get("levels", [])
                ],
            }
        except Exception:
            pass
    return result


def load_neetcode_display() -> dict[str, str]:
    """Return {pattern_slug: display_name} from neetcode150.yaml."""
    if not NEETCODE_YAML.exists():
        return {}
    try:
        patterns = yaml.safe_load(NEETCODE_YAML.read_text(encoding="utf-8"))
        return {p["pattern"]: p.get("display", p["pattern"]) for p in patterns}
    except Exception:
        return {}


def group_by_domain(syllabuses: dict[str, dict]) -> dict[str, dict[str, dict]]:
    """
    Returns nested dict: {domain: {subject_slug: subject_dict}}.
    Parents appear before their children within each domain.
    Order within a domain: parents first (no parent field), then children sorted by parent slug.
    """
    grouped: dict[str, dict[str, dict]] = {}
    for slug, subj in syllabuses.items():
        domain = subj["domain"]
        grouped.setdefault(domain, {})
        grouped[domain][slug] = subj

    # Sort domains by display priority
    domain_order = list(_DOMAIN_DISPLAY.keys())
    return dict(
        sorted(grouped.items(), key=lambda kv: domain_order.index(kv[0]) if kv[0] in domain_order else 99)
    )


def domain_display_name(domain: str) -> str:
    return _DOMAIN_DISPLAY.get(domain, domain.replace("_", " ").title())


def collect_neetcode_patterns(syllabuses: dict[str, dict], subject_slugs: list[str], level_min: int, level_max: int) -> list[str]:
    """Collect neetcode_patterns for subject slugs within a level range (legacy/drills use)."""
    seen: set[str] = set()
    patterns: list[str] = []
    for slug in subject_slugs:
        subj = syllabuses.get(slug)
        if not subj:
            continue
        for lvl in subj["levels"]:
            if level_min <= lvl["level"] <= level_max:
                for p in lvl["neetcode_patterns"]:
                    if p not in seen:
                        seen.add(p)
                        patterns.append(p)
    return patterns


def resolve_topic_levels(syllabuses: dict[str, dict], subject: str, topic: str) -> list[int]:
    """Return level numbers in a subject where level.topic == topic slug."""
    subj = syllabuses.get(subject)
    if not subj:
        return []
    return [lvl["level"] for lvl in subj["levels"] if lvl.get("topic") == topic]


def get_subject_topics(syllabuses: dict[str, dict]) -> dict[str, list[dict]]:
    """
    Returns {subject_slug: [{slug, display, neetcode_patterns}]}.
    Subjects with no topic-tagged levels return an empty list.
    """
    result: dict[str, list[dict]] = {}
    for slug, subj in syllabuses.items():
        seen: dict[str, dict] = {}
        for lvl in subj["levels"]:
            t = lvl.get("topic")
            if not t:
                continue
            if t not in seen:
                seen[t] = {
                    "slug": t,
                    "display": t.replace("_", " ").title(),
                    "neetcode_patterns": list(lvl["neetcode_patterns"]),
                }
            else:
                for p in lvl["neetcode_patterns"]:
                    if p not in seen[t]["neetcode_patterns"]:
                        seen[t]["neetcode_patterns"].append(p)
        result[slug] = list(seen.values())
    return result


def resolve_prerequisites(syllabuses: dict[str, dict]) -> dict[str, dict]:
    """Annotate every prerequisite (subject-wide and per-level) with a status:
    ``linked`` if the target syllabus slug exists, else ``proposed``.

    Proposed links are a feature — they are the backlog of which fundamentals
    syllabus to author next (e.g. a biopoly course that wants ``chemistry``).
    Mutates the dicts in place and returns the same mapping.
    """
    known = set(syllabuses.keys())

    def _mark(pres: list) -> None:
        for pre in pres or []:
            if isinstance(pre, dict):
                pre["status"] = "linked" if pre.get("subject") in known else "proposed"

    for subj in syllabuses.values():
        _mark(subj.get("prerequisites", []))
        for lvl in subj.get("levels", []):
            _mark(lvl.get("prerequisites", []))
    return syllabuses


def fundamentals_catalog(syllabuses: dict[str, dict]) -> list[dict]:
    """Compact catalog of existing syllabuses for the syllabus-generation prompt,
    so generated prerequisites link to fundamentals that actually exist.

    Returns [{slug, domain, title, levels: [{level, title}]}].
    """
    return [
        {
            "slug": slug,
            "domain": subj["domain"],
            "title": subj["title"],
            "levels": [
                {"level": lvl["level"], "title": lvl["title"]} for lvl in subj["levels"]
            ],
        }
        for slug, subj in syllabuses.items()
    ]


def collect_neetcode_patterns_by_topics(
    syllabuses: dict[str, dict], selections: list[dict]
) -> list[str]:
    """
    Given topic_config selections, return deduplicated NeetCode pattern slugs
    for the selected topics. selections = [{"subject": "dsa", "topic": "trees"}, ...]
    """
    seen: set[str] = set()
    patterns: list[str] = []
    for sel in selections:
        subj_slug = sel.get("subject", "")
        topic = sel.get("topic")
        subj = syllabuses.get(subj_slug)
        if not subj:
            continue
        for lvl in subj["levels"]:
            if topic and lvl.get("topic") != topic:
                continue
            for p in lvl.get("neetcode_patterns", []):
                if p not in seen:
                    seen.add(p)
                    patterns.append(p)
    return patterns
