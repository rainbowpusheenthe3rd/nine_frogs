"""Nine Frog Labs Celery tasks — test execution and report cards."""
from __future__ import annotations

import sys
from pathlib import Path

# Ensure project root is on sys.path regardless of where Celery is invoked from
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import logging
from datetime import date, datetime, timezone

from celery import Celery

from config import settings

celery_app = Celery(
    "ninefrogs_lab",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)
celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
)

logger = logging.getLogger(__name__)

# Path to the lab conftest used when running drills-style tests
_CONFTEST_PATH = Path(__file__).parent / "_lab_conftest.py"

_LAB_CONFTEST = '''\
"""Lab conftest — load submission.py from the temp directory."""
import importlib.util
from pathlib import Path
from fastapi import FastAPI
from fastapi.testclient import TestClient


def load_submission():
    p = Path(__file__).parent / "submission.py"
    spec = importlib.util.spec_from_file_location("submission", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def make_client(mod, exception_handlers=None):
    app = FastAPI()
    app.include_router(mod.router)
    if exception_handlers:
        for exc_cls, handler in exception_handlers:
            app.add_exception_handler(exc_cls, handler)
    return TestClient(app, raise_server_exceptions=False)
'''


def _ensure_lab_conftest() -> None:
    if not _CONFTEST_PATH.exists():
        _CONFTEST_PATH.write_text(_LAB_CONFTEST, encoding="utf-8")


def _make_drills_test_code(raw_test_code: str) -> str:
    """
    Rewrite drills-style test code so it works in a flat temp directory.

    Original tests do:
        import sys; sys.path.insert(0, str(Path(__file__).parent.parent))
        from conftest import load_submission

    We replace that header with an inline conftest so the test is self-contained.
    """
    inline_conftest = (
        "import importlib.util, pathlib\n"
        "def load_submission():\n"
        "    p = pathlib.Path(__file__).parent / 'submission.py'\n"
        "    spec = importlib.util.spec_from_file_location('submission', p)\n"
        "    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m\n"
        "def make_client(mod, exception_handlers=None):\n"
        "    from fastapi import FastAPI; from fastapi.testclient import TestClient\n"
        "    app = FastAPI(); app.include_router(mod.router)\n"
        "    if exception_handlers:\n"
        "        for exc, h in exception_handlers: app.add_exception_handler(exc, h)\n"
        "    return TestClient(app, raise_server_exceptions=False)\n"
    )

    import re
    # Strip the sys.path insert + from conftest import ... header
    cleaned = re.sub(
        r"^import sys;?\s*sys\.path\.insert\(.*?\)\s*\n",
        "",
        raw_test_code,
        flags=re.MULTILINE,
    )
    cleaned = re.sub(
        r"^from conftest import.*\n",
        "",
        cleaned,
        flags=re.MULTILINE,
    )
    return inline_conftest + "\n" + cleaned


def _is_drills_style(test_code: str) -> bool:
    return "load_submission" in test_code and "from conftest import" in test_code


# ── Task: run a single submission ─────────────────────────────────────────────

@celery_app.task(bind=True, name="lab.run_submission")
def run_submission(self, attempt_id: str) -> dict:
    """Run the code submission for a CodingAttempt and update SM-2 state."""
    import tempfile
    from pathlib import Path as _Path

    from lab.runner import (
        DOCKER_AVAILABLE,
        ExecutionResult,
        run_docker_app_challenge,
        run_docker_service_challenge,
        run_pytest_challenge,
        run_rust_challenge,
    )
    from lab.sm2 import next_due, rating_from_attempt, review

    result = asyncio.run(_run_submission_async(attempt_id))
    return result


async def _run_submission_async(attempt_id: str) -> dict:
    import tempfile
    from pathlib import Path as _Path

    from sqlalchemy import select

    from db.engine import async_session_factory
    from db.models import ChallengeProgress, CodingAttempt, CodingChallenge
    from lab.runner import (
        run_docker_app_challenge,
        run_docker_service_challenge,
        run_pytest_challenge,
        run_rust_challenge,
    )
    from lab.sm2 import next_due, rating_from_attempt, review

    async with async_session_factory() as session:
        attempt = await session.get(CodingAttempt, attempt_id)
        if not attempt:
            return {"error": "Attempt not found"}

        challenge = await session.get(CodingChallenge, attempt.challenge_id)
        if not challenge:
            return {"error": "Challenge not found"}

        code = attempt.code_submitted or ""
        test_code = challenge.test_code or ""
        ctype = challenge.type

        # Adapt drills-style tests to flat temp dir
        if _is_drills_style(test_code):
            test_code = _make_drills_test_code(test_code)

        # Dispatch to correct runner
        if ctype == "rust":
            from lab.runner import run_rust_challenge
            exec_result = run_rust_challenge(code, test_code)
        elif ctype == "docker_app" and challenge.docker_config:
            cfg = challenge.docker_config
            exec_result = run_docker_app_challenge(
                submission_code=code,
                test_code=test_code,
                port=cfg.get("port", 8900),
                base_image=cfg.get("base_image", "python:3.11-slim"),
                requirements=cfg.get("requirements", ["fastapi", "uvicorn"]),
            )
        elif ctype == "docker_service" and challenge.docker_config:
            cfg = challenge.docker_config
            exec_result = run_docker_service_challenge(
                submission_code=code,
                test_code=test_code,
                compose_file=cfg.get("compose_file", ""),
                services=cfg.get("services", []),
            )
        else:
            exec_result = run_pytest_challenge(code, test_code, timeout=30)

        passed = exec_result.passed > 0 and exec_result.failed == 0
        now = datetime.now(timezone.utc)

        attempt.submitted_at = now
        attempt.status = "passed" if passed else "failed"
        attempt.test_output = exec_result.output or exec_result.error
        if attempt.started_at:
            delta = (now - attempt.started_at).total_seconds()
            attempt.time_spent_seconds = int(delta)

        # Update ChallengeProgress (SM-2) — skipped for practice attempts
        prog = None
        if not attempt.is_practice:
            prog = await session.scalar(
                select(ChallengeProgress).where(
                    ChallengeProgress.challenge_id == challenge.id
                )
            )
            if not prog:
                prog = ChallengeProgress(
                    challenge_id=challenge.id,
                    sm2_ef=2.5,
                    sm2_interval=1,
                    sm2_repetitions=0,
                    total_attempts=0,
                    total_passes=0,
                )
                session.add(prog)

            from lab.sm2 import next_due, rating_from_attempt, review
            rating = rating_from_attempt(passed, attempt.hints_used)
            new_ef, new_interval, new_reps = review(
                prog.sm2_ef, prog.sm2_interval, prog.sm2_repetitions, rating
            )
            prog.sm2_ef = new_ef
            prog.sm2_interval = new_interval
            prog.sm2_repetitions = new_reps
            prog.next_review = next_due(new_interval)
            prog.total_attempts += 1
            if passed:
                prog.total_passes += 1
            prog.last_attempted_at = now

        # Update CampaignEntry if this attempt belongs to a campaign
        if attempt.campaign_id:
            from db.models import CampaignEntry
            entry = await session.scalar(
                select(CampaignEntry).where(
                    CampaignEntry.campaign_id == attempt.campaign_id,
                    CampaignEntry.challenge_id == challenge.id,
                )
            )
            if entry:
                entry.status = attempt.status
                entry.attempt_id = attempt.id
                entry.time_spent_seconds = attempt.time_spent_seconds

        await session.commit()

        return {
            "attempt_id": str(attempt.id),
            "status": attempt.status,
            "passed": passed,
            "test_output": attempt.test_output,
            "time_spent_seconds": attempt.time_spent_seconds,
            "next_review": prog.next_review.isoformat() if prog and prog.next_review else None,
        }


# ── Task: generate a report card ──────────────────────────────────────────────

@celery_app.task(name="lab.generate_report_card")
def generate_report_card(since_iso: str | None = None) -> dict:
    return asyncio.run(_report_card_async(since_iso))


async def _report_card_async(since_iso: str | None) -> dict:
    from datetime import timedelta

    from sqlalchemy import func, select

    from db.engine import async_session_factory
    from db.models import CodingAttempt

    since = (
        datetime.fromisoformat(since_iso)
        if since_iso
        else datetime.now(timezone.utc) - timedelta(hours=24)
    )

    async with async_session_factory() as session:
        attempts = (await session.scalars(
            select(CodingAttempt).where(
                CodingAttempt.submitted_at >= since,
                CodingAttempt.status.in_(["passed", "failed", "gave_up"]),
            )
        )).all()

    total = len(attempts)
    if total == 0:
        return {"total": 0, "passed": 0, "failed": 0, "gave_up": 0,
                "pass_rate": 0.0, "avg_time_seconds": None, "subjects": {}}

    passed = sum(1 for a in attempts if a.status == "passed")
    failed = sum(1 for a in attempts if a.status == "failed")
    gave_up = sum(1 for a in attempts if a.status == "gave_up")
    times = [a.time_spent_seconds for a in attempts if a.time_spent_seconds]
    avg_time = sum(times) / len(times) if times else None

    return {
        "total": total,
        "passed": passed,
        "failed": failed,
        "gave_up": gave_up,
        "pass_rate": round(passed / total, 2),
        "avg_time_seconds": round(avg_time) if avg_time else None,
    }
