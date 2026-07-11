"""Nine Frog Labs challenge importer.

Sources:
  1. Local YAML exercises from D:\\Organiser\\drills\\exercises
  2. HuggingFace Tier-1: mbpp (sanitized), evalplus/humanevalplus, newfacade/LeetCodeDataset

Run: python -m lab.importer [--source yaml|mbpp|humaneval|leetcode|all]
"""
from __future__ import annotations

import argparse
import ast
import asyncio
import logging
import re
from pathlib import Path

import yaml
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

DRILLS_ROOT = Path(__file__).parent.parent.parent.parent.parent / "Organiser" / "drills"
EXERCISES_DIR = DRILLS_ROOT / "exercises"
TESTS_DIR = DRILLS_ROOT / "tests"


# ── DB helpers ────────────────────────────────────────────────────────────────

async def _upsert_challenge(session: AsyncSession, data: dict) -> None:
    from db.models import CodingChallenge

    slug = data["slug"]
    existing = await session.scalar(
        select(CodingChallenge).where(CodingChallenge.slug == slug)
    )
    if existing:
        for k, v in data.items():
            if k != "slug":
                setattr(existing, k, v)
    else:
        session.add(CodingChallenge(**data))


# ── 1. Local YAML exercises ───────────────────────────────────────────────────

def _load_test_code(test_file_rel: str) -> str:
    """Load test file content; return placeholder if missing."""
    path = DRILLS_ROOT / test_file_rel
    if path.exists():
        return path.read_text(encoding="utf-8")
    # Try alternate location: tests/<subject>/<filename>
    parts = Path(test_file_rel).parts
    if len(parts) >= 2:
        alt = TESTS_DIR / Path(*parts[1:])
        if alt.exists():
            return alt.read_text(encoding="utf-8")
    return f"# Test file not found: {test_file_rel}\n"


async def import_yaml_exercises(session: AsyncSession) -> int:
    if not EXERCISES_DIR.exists():
        logger.warning("Exercises dir not found: %s", EXERCISES_DIR)
        return 0

    count = 0
    for yaml_file in sorted(EXERCISES_DIR.rglob("*.yaml")):
        try:
            raw = yaml.safe_load(yaml_file.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning("Skipping %s: %s", yaml_file, e)
            continue

        slug = raw.get("id") or yaml_file.stem
        hints = raw.get("hints") or []
        # Pad to 3 hints
        while len(hints) < 3:
            hints.append("")

        test_code = ""
        if raw.get("test_file"):
            test_code = _load_test_code(raw["test_file"])

        await _upsert_challenge(session, {
            "slug": slug,
            "source": "drills_yaml",
            "subject": raw.get("subject", "python"),
            "level": raw.get("level"),
            "difficulty": raw.get("difficulty", 1),
            "type": raw.get("type", "module"),
            "title": raw.get("title", slug),
            "prompt": raw.get("prompt", ""),
            "starter_code": None,
            "hints": hints[:3],
            "test_code": test_code,
            "solution_code": None,
            "docker_config": None,
            "tags": [],
        })
        count += 1

    await session.commit()
    logger.info("Imported %d YAML exercises.", count)
    return count


# ── 2. MBPP (sanitized) ───────────────────────────────────────────────────────

def _mbpp_assertions_to_pytest(test_list: list[str], solution_code: str) -> str:
    """Wrap MBPP assertion strings into a pytest test that imports submission."""
    lines = [
        "import sys, importlib.util, pathlib",
        "def _load():",
        "    p = pathlib.Path(__file__).parent / 'submission.py'",
        "    spec = importlib.util.spec_from_file_location('submission', p)",
        "    m = importlib.util.module_from_spec(spec)",
        "    spec.loader.exec_module(m)",
        "    return m",
        "",
        "# Extract function name from solution",
    ]
    # Find function names defined in the solution
    func_names: list[str] = []
    try:
        tree = ast.parse(solution_code)
        func_names = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    except Exception:
        pass

    lines += [
        "def test_mbpp():",
        "    mod = _load()",
    ]
    for fn in func_names:
        lines.append(f"    {fn} = mod.{fn}")

    for assertion in test_list:
        # Indent assertion under the test function
        assertion_clean = assertion.strip()
        if assertion_clean:
            lines.append(f"    {assertion_clean}")

    return "\n".join(lines) + "\n"


async def import_mbpp(session: AsyncSession) -> int:
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("datasets not installed — run: pip install datasets")
        return 0

    logger.info("Loading MBPP sanitized dataset…")
    try:
        ds = load_dataset("google-research-datasets/mbpp", "sanitized", split="train+test+validation")
    except Exception as e:
        logger.error("Failed to load MBPP: %s", e)
        return 0

    count = 0
    for row in ds:
        slug = f"mbpp_{row['task_id']:04d}"
        test_code = _mbpp_assertions_to_pytest(row["test_list"], row["code"])
        hints = ["", "", ""]

        await _upsert_challenge(session, {
            "slug": slug,
            "source": "mbpp",
            "subject": "python",
            "level": None,
            "difficulty": 1,
            "type": "function",
            "title": f"MBPP #{row['task_id']}",
            "prompt": row.get("text") or row.get("prompt") or "",
            "starter_code": None,
            "hints": hints,
            "test_code": test_code,
            "solution_code": row["code"],
            "docker_config": None,
            "tags": ["mbpp", "python-fundamentals"],
        })
        count += 1

    await session.commit()
    logger.info("Imported %d MBPP challenges.", count)
    return count


# ── 3. HumanEval+ (evalplus/humanevalplus) ────────────────────────────────────

def _humaneval_test_to_pytest(entry_point: str, test_block: str) -> str:
    """Wrap HumanEval test block into a pytest test importing submission."""
    lines = [
        "import sys, importlib.util, pathlib",
        "def _load():",
        "    p = pathlib.Path(__file__).parent / 'submission.py'",
        "    spec = importlib.util.spec_from_file_location('submission', p)",
        "    m = importlib.util.module_from_spec(spec)",
        "    spec.loader.exec_module(m)",
        "    return m",
        "",
        f"def test_humaneval_{entry_point}():",
        f"    {entry_point} = _load().{entry_point}",
    ]
    # Indent the test block
    for line in test_block.splitlines():
        stripped = line.rstrip()
        if stripped:
            lines.append(f"    {stripped}")
        else:
            lines.append("")
    return "\n".join(lines) + "\n"


async def import_humaneval(session: AsyncSession) -> int:
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("datasets not installed")
        return 0

    logger.info("Loading HumanEval+ dataset…")
    try:
        ds = load_dataset("evalplus/humanevalplus", split="test")
    except Exception as e:
        logger.error("Failed to load HumanEval+: %s", e)
        return 0

    count = 0
    for row in ds:
        task_id = row["task_id"].replace("/", "_").lower()
        slug = f"he_{task_id}"
        entry = row["entry_point"]
        test_code = _humaneval_test_to_pytest(entry, row["test"])

        await _upsert_challenge(session, {
            "slug": slug,
            "source": "humaneval",
            "subject": "python",
            "level": None,
            "difficulty": 2,
            "type": "function",
            "title": f"HumanEval {row['task_id']}",
            "prompt": row["prompt"],
            "starter_code": row["prompt"],
            "hints": ["", "", ""],
            "test_code": test_code,
            "solution_code": row["canonical_solution"],
            "docker_config": None,
            "tags": ["humaneval", "algorithms"],
        })
        count += 1

    await session.commit()
    logger.info("Imported %d HumanEval+ challenges.", count)
    return count


# ── 4. Neetcode 150 (curated algorithm curriculum) ───────────────────────────

NEETCODE_YAML = Path(__file__).parent / "neetcode150.yaml"


def _lc_check_to_pytest(entry_point: str, check_fn: str) -> str:
    """Wrap a LeetCode check(candidate) block into a runnable pytest file."""
    if "." in entry_point:
        # e.g. "Solution().twoSum" → class=Solution, method=twoSum
        cls = entry_point.split("(")[0]
        method = entry_point.rsplit(".", 1)[-1]
        setup = f"    candidate = _load().{cls}().{method}"
    else:
        setup = f"    candidate = _load().{entry_point}"

    return "\n".join([
        "import importlib.util, pathlib",
        "",
        "def _load():",
        "    p = pathlib.Path(__file__).parent / 'submission.py'",
        "    spec = importlib.util.spec_from_file_location('submission', p)",
        "    m = importlib.util.module_from_spec(spec)",
        "    spec.loader.exec_module(m)",
        "    return m",
        "",
        check_fn.rstrip(),
        "",
        "def test_neetcode():",
        setup,
        "    check(candidate)",
    ]) + "\n"


async def import_neetcode(session: AsyncSession) -> int:
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("datasets not installed")
        return 0

    if not NEETCODE_YAML.exists():
        logger.error("neetcode150.yaml not found at %s", NEETCODE_YAML)
        return 0

    patterns = yaml.safe_load(NEETCODE_YAML.read_text(encoding="utf-8"))

    logger.info("Loading LeetCode dataset for Neetcode lookup…")
    try:
        ds = load_dataset("newfacade/LeetCodeDataset", split="train")
    except Exception as e:
        logger.error("Failed to load LeetCode dataset: %s", e)
        return 0

    # Build lookup keyed by question_id (integer LC problem number)
    lc_by_id: dict[int, dict] = {}
    for row in ds:
        qid = row.get("question_id")
        if qid is not None:
            lc_by_id[int(qid)] = dict(row)

    logger.info("Loaded %d LeetCode rows; importing Neetcode 150…", len(lc_by_id))

    diff_map = {"easy": 1, "medium": 2, "hard": 3}
    count = 0
    skipped = 0

    for pat in patterns:
        pattern_slug = pat["pattern"]

        for prob in pat["problems"]:
            lc_id = int(prob["lc_id"])
            row = lc_by_id.get(lc_id)

            if row is None:
                logger.warning("LC #%d (%s) not found in dataset — skipping", lc_id, prob["title"])
                skipped += 1
                continue

            entry_point = row.get("entry_point") or ""
            raw_test = row.get("test") or ""
            if raw_test and entry_point:
                test_code = _lc_check_to_pytest(entry_point, raw_test)
            elif raw_test:
                test_code = raw_test
            else:
                test_code = "def test_placeholder():\n    pass\n"

            raw_diff = str(row.get("difficulty", "medium")).lower()
            difficulty = diff_map.get(raw_diff, prob.get("difficulty", 2))

            slug = f"neetcode_{lc_id}"
            title = prob.get("title") or row.get("title") or slug

            await _upsert_challenge(session, {
                "slug": slug,
                "source": "neetcode",
                "subject": pattern_slug,
                "pattern": pattern_slug,
                "level": prob["level"],
                "difficulty": difficulty,
                "type": "function",
                "title": title,
                "prompt": row.get("problem_description") or row.get("content") or "",
                "starter_code": row.get("starter_code") or "",
                "hints": ["", "", ""],
                "test_code": test_code,
                "solution_code": row.get("completion") or row.get("solution") or "",
                "docker_config": None,
                "tags": ["neetcode", "algorithms", pattern_slug],
            })
            count += 1

    await session.commit()
    logger.info("Imported %d Neetcode challenges (%d skipped).", count, skipped)
    return count


# ── 5. LeetCode (newfacade/LeetCodeDataset) ───────────────────────────────────

async def import_leetcode(session: AsyncSession) -> int:
    try:
        from datasets import load_dataset
    except ImportError:
        logger.error("datasets not installed")
        return 0

    logger.info("Loading LeetCode dataset…")
    try:
        ds = load_dataset("newfacade/LeetCodeDataset", split="train")
    except Exception as e:
        logger.error("Failed to load LeetCode dataset: %s", e)
        return 0

    diff_map = {"easy": 1, "medium": 2, "hard": 3}
    count = 0
    for row in ds:
        task_id = row.get("task_id") or row.get("id") or count
        slug = f"lc_{task_id}"
        difficulty = diff_map.get(str(row.get("difficulty", "medium")).lower(), 2)

        # Test code: LeetCode dataset provides test cases as assertions or I/O
        test_code = row.get("test", "") or ""
        if not test_code:
            test_code = "# No automated tests available for this problem.\ndef test_placeholder():\n    pass\n"

        await _upsert_challenge(session, {
            "slug": slug,
            "source": "leetcode",
            "subject": "algorithms",
            "level": None,
            "difficulty": difficulty,
            "type": "function",
            "title": row.get("title", slug),
            "prompt": row.get("content") or row.get("question") or "",
            "starter_code": row.get("starter_code") or row.get("code_snippet"),
            "hints": ["", "", ""],
            "test_code": test_code,
            "solution_code": row.get("solution") or row.get("python_solution"),
            "docker_config": None,
            "tags": ["leetcode"] + (row.get("tags") or []),
        })
        count += 1

    await session.commit()
    logger.info("Imported %d LeetCode challenges.", count)
    return count


# ── Main ──────────────────────────────────────────────────────────────────────

async def run_import(sources: list[str]) -> None:
    from db.engine import async_session_factory
    import db.models  # noqa: F401 — populate metadata

    async with async_session_factory() as session:
        totals: dict[str, int] = {}

        if "yaml" in sources or "all" in sources:
            totals["yaml"] = await import_yaml_exercises(session)

        if "mbpp" in sources or "all" in sources:
            totals["mbpp"] = await import_mbpp(session)

        if "humaneval" in sources or "all" in sources:
            totals["humaneval"] = await import_humaneval(session)

        if "neetcode" in sources or "all" in sources:
            totals["neetcode"] = await import_neetcode(session)

        if "leetcode" in sources or "all" in sources:
            totals["leetcode"] = await import_leetcode(session)

    print("\nImport complete:")
    for source, n in totals.items():
        print(f"  {source:12s} {n:>5d} challenges")
    print(f"  {'TOTAL':12s} {sum(totals.values()):>5d} challenges")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(description="Nine Frog Labs challenge importer")
    parser.add_argument(
        "--source",
        nargs="+",
        choices=["yaml", "mbpp", "humaneval", "neetcode", "leetcode", "all"],
        default=["yaml"],
        help="Which source(s) to import (default: yaml)",
    )
    args = parser.parse_args()
    asyncio.run(run_import(args.source))


if __name__ == "__main__":
    main()
