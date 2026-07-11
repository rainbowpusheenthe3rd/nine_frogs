"""Nine Frog Labs routes — /lab/**"""
from __future__ import annotations

import asyncio
import json
import uuid
from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse, StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import (
    Campaign,
    CampaignEntry,
    ChallengeProgress,
    CodingAttempt,
    CodingChallenge,
)
from lab.runner import DOCKER_AVAILABLE
from lab.subjects import (
    collect_neetcode_patterns_by_topics,
    domain_display_name,
    get_subject_topics,
    group_by_domain,
    load_all_syllabuses,
    load_neetcode_display,
    resolve_topic_levels,
)
from web.dependencies import get_db
from web.templating import templates

router = APIRouter()


def _subject_display() -> dict[str, str]:
    """Merged display names: YAML syllabuses + NeetCode patterns."""
    display = load_neetcode_display()
    for slug, subj in load_all_syllabuses().items():
        display.setdefault(slug, subj["title"].split(":")[0].strip())
    return display


# ── Helpers ───────────────────────────────────────────────────────────────────

def _diff_label(d: int) -> str:
    return {1: "easy", 2: "medium", 3: "hard"}.get(d, "medium")


async def _get_challenge(slug: str, db: AsyncSession) -> CodingChallenge:
    ch = await db.scalar(select(CodingChallenge).where(CodingChallenge.slug == slug))
    if not ch:
        raise HTTPException(status_code=404, detail="Challenge not found")
    return ch


async def _active_attempt(
    challenge_id: uuid.UUID, db: AsyncSession
) -> CodingAttempt | None:
    return await db.scalar(
        select(CodingAttempt)
        .where(
            CodingAttempt.challenge_id == challenge_id,
            CodingAttempt.status == "in_progress",
        )
        .order_by(CodingAttempt.started_at.desc())
        .limit(1)
    )


# ── Dashboard ─────────────────────────────────────────────────────────────────

@router.get("/", response_class=HTMLResponse)
async def dashboard(request: Request, db: AsyncSession = Depends(get_db)):
    active_campaigns = (await db.scalars(
        select(Campaign)
        .where(Campaign.status == "active")
        .order_by(Campaign.last_active_at.desc())
        .options(selectinload(Campaign.entries))
    )).all()

    due_count = await db.scalar(
        select(func.count()).select_from(ChallengeProgress).where(
            ChallengeProgress.next_review <= date.today()
        )
    ) or 0

    recent_attempts = (await db.scalars(
        select(CodingAttempt)
        .where(CodingAttempt.status.in_(["passed", "failed", "gave_up"]))
        .order_by(CodingAttempt.submitted_at.desc())
        .limit(10)
    )).all()

    total_challenges = await db.scalar(select(func.count()).select_from(CodingChallenge)) or 0

    return templates.TemplateResponse("lab/dashboard.html", {
        "request": request,
        "active_campaigns": active_campaigns,
        "due_count": due_count,
        "recent_attempts": recent_attempts,
        "total_challenges": total_challenges,
        "docker_available": DOCKER_AVAILABLE,
    })


# ── Challenge list / browse ───────────────────────────────────────────────────

@router.get("/challenges", response_class=HTMLResponse)
async def challenge_list(
    request: Request,
    subject: str = "",
    difficulty: int = 0,
    source: str = "",
    hide_docker: bool = False,
    db: AsyncSession = Depends(get_db),
):
    q = select(CodingChallenge).order_by(
        CodingChallenge.subject, CodingChallenge.level.nullslast(), CodingChallenge.difficulty
    )
    if subject:
        q = q.where(CodingChallenge.subject == subject)
    if difficulty:
        q = q.where(CodingChallenge.difficulty == difficulty)
    if source:
        q = q.where(CodingChallenge.source == source)
    if hide_docker or not DOCKER_AVAILABLE:
        q = q.where(CodingChallenge.docker_config.is_(None))

    challenges = (await db.scalars(q)).all()

    subjects = (await db.scalars(
        select(CodingChallenge.subject).distinct().order_by(CodingChallenge.subject)
    )).all()

    sources = (await db.scalars(
        select(CodingChallenge.source).distinct().order_by(CodingChallenge.source)
    )).all()

    return templates.TemplateResponse("lab/challenges_list.html", {
        "request": request,
        "challenges": challenges,
        "subjects": subjects,
        "sources": sources,
        "filter_subject": subject,
        "filter_difficulty": difficulty,
        "filter_source": source,
        "hide_docker": hide_docker,
        "docker_available": DOCKER_AVAILABLE,
        "diff_label": _diff_label,
    })


# ── Single challenge page ─────────────────────────────────────────────────────

@router.get("/challenges/{slug}", response_class=HTMLResponse)
async def challenge_page(
    slug: str,
    request: Request,
    campaign_id: str = "",
    db: AsyncSession = Depends(get_db),
):
    ch = await _get_challenge(slug, db)
    prog = await db.scalar(
        select(ChallengeProgress).where(ChallengeProgress.challenge_id == ch.id)
    )
    active = await _active_attempt(ch.id, db)

    campaign = None
    if campaign_id:
        campaign = await db.get(Campaign, uuid.UUID(campaign_id))

    return templates.TemplateResponse("lab/challenge.html", {
        "request": request,
        "challenge": ch,
        "progress": prog,
        "active_attempt": active,
        "campaign": campaign,
        "docker_available": DOCKER_AVAILABLE,
        "diff_label": _diff_label,
    })


# ── Start an attempt ──────────────────────────────────────────────────────────

@router.post("/challenges/{slug}/start")
async def start_attempt(
    slug: str,
    request: Request,
    campaign_id: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    ch = await _get_challenge(slug, db)

    # Reuse existing in-progress attempt if any
    existing = await _active_attempt(ch.id, db)
    if existing:
        return RedirectResponse(f"/lab/challenges/{slug}?attempt_id={existing.id}", status_code=303)

    # Inherit is_practice from campaign if present
    is_practice = False
    if campaign_id:
        campaign_obj = await db.get(Campaign, uuid.UUID(campaign_id))
        if campaign_obj:
            is_practice = campaign_obj.is_practice

    attempt = CodingAttempt(
        challenge_id=ch.id,
        campaign_id=uuid.UUID(campaign_id) if campaign_id else None,
        is_practice=is_practice,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(attempt)

    return RedirectResponse(
        f"/lab/challenges/{slug}?attempt_id={attempt.id}"
        + (f"&campaign_id={campaign_id}" if campaign_id else ""),
        status_code=303,
    )


# ── Unlock a hint ─────────────────────────────────────────────────────────────

@router.post("/challenges/{slug}/notes", response_class=HTMLResponse)
async def save_notes(
    slug: str,
    notes: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    ch = await _get_challenge(slug, db)
    prog = await db.scalar(select(ChallengeProgress).where(ChallengeProgress.challenge_id == ch.id))
    if not prog:
        prog = ChallengeProgress(
            challenge_id=ch.id, sm2_ef=2.5, sm2_interval=1, sm2_repetitions=0,
            total_attempts=0, total_passes=0,
        )
        db.add(prog)
    prog.notes = notes.strip() or None
    await db.commit()
    return HTMLResponse('<span style="color:var(--green);font-size:.78rem">✓ saved</span>')


@router.post("/challenges/{slug}/hint/{n}", response_class=HTMLResponse)
async def unlock_hint(
    slug: str,
    n: int,
    attempt_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    if n not in (1, 2, 3):
        raise HTTPException(status_code=400, detail="Hint index must be 1, 2, or 3")

    ch = await _get_challenge(slug, db)
    attempt = await db.get(CodingAttempt, uuid.UUID(attempt_id))
    if not attempt or str(attempt.challenge_id) != str(ch.id):
        raise HTTPException(status_code=404, detail="Attempt not found")

    if attempt.hints_used < n:
        attempt.hints_used = n
        await db.commit()

    hints = ch.hints or []
    hint_text = hints[n - 1] if n <= len(hints) else ""
    return HTMLResponse(f'<p class="hint-text">{hint_text}</p>')


# ── Submit code ───────────────────────────────────────────────────────────────

@router.post("/challenges/{slug}/submit")
async def submit_challenge(
    slug: str,
    attempt_id: str = Form(...),
    code: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    ch = await _get_challenge(slug, db)
    attempt = await db.get(CodingAttempt, uuid.UUID(attempt_id))
    if not attempt or str(attempt.challenge_id) != str(ch.id):
        raise HTTPException(status_code=404, detail="Attempt not found")

    attempt.code_submitted = code
    attempt.status = "in_progress"
    await db.commit()

    # Enqueue Celery task
    from lab.tasks import run_submission
    run_submission.delay(str(attempt.id))

    return {"attempt_id": str(attempt.id), "status": "queued"}


# ── Give up ───────────────────────────────────────────────────────────────────

@router.post("/challenges/{slug}/give-up", response_class=HTMLResponse)
async def give_up(
    slug: str,
    attempt_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    ch = await _get_challenge(slug, db)
    attempt = await db.get(CodingAttempt, uuid.UUID(attempt_id))
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    now = datetime.now(timezone.utc)
    attempt.status = "gave_up"
    attempt.submitted_at = now
    if attempt.started_at:
        attempt.time_spent_seconds = int((now - attempt.started_at).total_seconds())

    # Update SM-2 with rating 0 (blackout)
    from lab.sm2 import next_due, review
    from sqlalchemy import select as _select
    prog = await db.scalar(
        _select(ChallengeProgress).where(ChallengeProgress.challenge_id == ch.id)
    )
    if not prog:
        prog = ChallengeProgress(
            challenge_id=ch.id,
            sm2_ef=2.5,
            sm2_interval=1,
            sm2_repetitions=0,
        )
        db.add(prog)
    new_ef, new_interval, new_reps = review(prog.sm2_ef, prog.sm2_interval, prog.sm2_repetitions, 0)
    prog.sm2_ef = new_ef
    prog.sm2_interval = new_interval
    prog.sm2_repetitions = new_reps
    prog.next_review = next_due(new_interval)
    prog.total_attempts += 1
    prog.last_attempted_at = now

    await db.commit()

    solution = ch.solution_code or "# No solution available."
    return HTMLResponse(
        f'<pre class="solution-reveal"><code>{solution}</code></pre>'
        f'<p class="gave-up-msg">Next review: {prog.next_review}</p>'
    )


# ── Poll attempt result ───────────────────────────────────────────────────────

@router.get("/attempts/{attempt_id}/result")
async def attempt_result(attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    attempt = await db.get(CodingAttempt, attempt_id)
    if not attempt:
        raise HTTPException(status_code=404, detail="Attempt not found")

    prog = await db.scalar(
        select(ChallengeProgress).where(ChallengeProgress.challenge_id == attempt.challenge_id)
    )

    return {
        "attempt_id": str(attempt.id),
        "status": attempt.status,
        "test_output": attempt.test_output,
        "time_spent_seconds": attempt.time_spent_seconds,
        "next_review": prog.next_review.isoformat() if prog and prog.next_review else None,
    }


# ── SSE stream for attempt result ─────────────────────────────────────────────

@router.get("/attempts/{attempt_id}/stream")
async def attempt_stream(attempt_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    async def generator():
        from db.engine import async_session_factory
        from db.models import ChallengeProgress, CodingAttempt

        for _ in range(60):  # poll up to 60s
            async with async_session_factory() as s:
                attempt = await s.get(CodingAttempt, attempt_id)
                if not attempt:
                    yield f"data: {json.dumps({'error': 'not found'})}\n\n"
                    return

                if attempt.status != "in_progress":
                    prog = await s.scalar(
                        select(ChallengeProgress).where(
                            ChallengeProgress.challenge_id == attempt.challenge_id
                        )
                    )
                    payload = {
                        "status": attempt.status,
                        "test_output": attempt.test_output,
                        "time_spent_seconds": attempt.time_spent_seconds,
                        "next_review": prog.next_review.isoformat() if prog and prog.next_review else None,
                    }
                    yield f"data: {json.dumps(payload)}\n\n"
                    return

                yield f"data: {json.dumps({'status': 'in_progress'})}\n\n"
            await asyncio.sleep(1)

        yield f"data: {json.dumps({'error': 'timed out waiting for result'})}\n\n"

    return StreamingResponse(
        generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ── Campaigns ─────────────────────────────────────────────────────────────────

@router.get("/campaigns", response_class=HTMLResponse)
async def campaigns_list(request: Request, db: AsyncSession = Depends(get_db)):
    campaigns = (await db.scalars(
        select(Campaign)
        .order_by(Campaign.last_active_at.desc())
        .options(selectinload(Campaign.entries))
    )).all()

    syllabuses = load_all_syllabuses()
    grouped = group_by_domain(syllabuses)
    subject_topics = get_subject_topics(syllabuses)
    subject_display = _subject_display()
    domain_names = {d: domain_display_name(d) for d in grouped}

    return templates.TemplateResponse("lab/campaigns.html", {
        "request": request,
        "campaigns": campaigns,
        "grouped": grouped,
        "domain_names": domain_names,
        "subject_topics": subject_topics,
        "subject_display": subject_display,
    })


@router.post("/campaigns/create")
async def create_campaign(
    request: Request,
    name: str = Form(default=""),
    is_practice: str = Form(default=""),
    db: AsyncSession = Depends(get_db),
):
    form = await request.form()
    # topic_sel values: "dsa::trees", "dsa::graphs", "fastapi" (no topic = whole subject)
    raw_selections = form.getlist("topic_sel")
    neetcode_difficulties = [int(d) for d in form.getlist("neetcode_difficulty") if d.isdigit()]

    selections: list[dict] = []
    for raw in raw_selections:
        if "::" in raw:
            subj, topic = raw.split("::", 1)
            selections.append({"subject": subj, "topic": topic})
        else:
            selections.append({"subject": raw})

    topic_config = {
        "selections": selections,
        "neetcode_difficulty": neetcode_difficulties,
    }

    # Derive display subjects list (unique subject slugs)
    subjects = list(dict.fromkeys(s["subject"] for s in selections))

    if not name:
        prefix = "[Practice] " if is_practice else ""
        topic_labels = [s.get("topic") or s["subject"] for s in selections]
        name = f"{prefix}{', '.join(topic_labels)} — {date.today().strftime('%b %Y')}"

    campaign = Campaign(
        name=name,
        subjects=subjects,
        topic_config=topic_config,
        is_practice=bool(is_practice),
    )
    db.add(campaign)
    await db.flush()

    syllabuses = load_all_syllabuses()
    challenges: list = []
    seen_ids: set = set()

    # Syllabus / drills challenges
    for sel in selections:
        subj = sel["subject"]
        topic = sel.get("topic")
        if topic:
            levels = resolve_topic_levels(syllabuses, subj, topic)
            if not levels:
                continue
            rows = (await db.scalars(
                select(CodingChallenge)
                .where(
                    CodingChallenge.subject == subj,
                    CodingChallenge.level.in_(levels),
                )
                .order_by(CodingChallenge.level, CodingChallenge.difficulty, CodingChallenge.slug)
            )).all()
        else:
            rows = (await db.scalars(
                select(CodingChallenge)
                .where(CodingChallenge.subject == subj)
                .order_by(CodingChallenge.level.nullslast(), CodingChallenge.difficulty, CodingChallenge.slug)
            )).all()
        for ch in rows:
            if ch.id not in seen_ids:
                seen_ids.add(ch.id)
                challenges.append(ch)

    # NeetCode challenges — resolved from topic neetcode_patterns, filtered by difficulty
    if neetcode_difficulties:
        patterns = collect_neetcode_patterns_by_topics(syllabuses, selections)
        if patterns:
            nc_rows = (await db.scalars(
                select(CodingChallenge)
                .where(
                    CodingChallenge.source == "neetcode",
                    CodingChallenge.pattern.in_(patterns),
                    CodingChallenge.difficulty.in_(neetcode_difficulties),
                )
                .order_by(CodingChallenge.pattern, CodingChallenge.level, CodingChallenge.difficulty)
            )).all()
            for ch in nc_rows:
                if ch.id not in seen_ids:
                    seen_ids.add(ch.id)
                    challenges.append(ch)

    for pos, ch in enumerate(challenges):
        db.add(CampaignEntry(
            campaign_id=campaign.id,
            challenge_id=ch.id,
            position=pos,
        ))

    await db.commit()
    await db.refresh(campaign)
    return RedirectResponse(f"/lab/campaigns/{campaign.id}", status_code=303)


@router.get("/campaigns/{campaign_id}", response_class=HTMLResponse)
async def campaign_detail(
    campaign_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")

    entries = (await db.scalars(
        select(CampaignEntry)
        .where(CampaignEntry.campaign_id == campaign_id)
        .order_by(CampaignEntry.position)
    )).all()

    # Load challenges for entries
    challenge_map: dict = {}
    for entry in entries:
        ch = await db.get(CodingChallenge, entry.challenge_id)
        if ch:
            challenge_map[str(entry.id)] = ch

    pending_count = sum(1 for e in entries if e.status == "pending")
    passed_count = sum(1 for e in entries if e.status == "passed")

    return templates.TemplateResponse("lab/campaign.html", {
        "request": request,
        "campaign": campaign,
        "entries": entries,
        "challenge_map": challenge_map,
        "pending_count": pending_count,
        "passed_count": passed_count,
        "total_count": len(entries),
        "subject_display": _subject_display(),
    })


@router.post("/campaigns/{campaign_id}/delete")
async def delete_campaign(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.delete(campaign)
    await db.commit()
    return RedirectResponse("/lab/campaigns", status_code=303)


@router.post("/campaigns/{campaign_id}/rename")
async def rename_campaign(
    campaign_id: uuid.UUID,
    name: str = Form(...),
    db: AsyncSession = Depends(get_db),
):
    campaign = await db.get(Campaign, campaign_id)
    if not campaign:
        raise HTTPException(status_code=404, detail="Campaign not found")
    campaign.name = name.strip()
    await db.commit()
    return {"name": campaign.name}


@router.get("/campaigns/{campaign_id}/next")
async def campaign_next(campaign_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    entry = await db.scalar(
        select(CampaignEntry)
        .where(
            CampaignEntry.campaign_id == campaign_id,
            CampaignEntry.status == "pending",
        )
        .order_by(CampaignEntry.position)
        .limit(1)
    )
    if not entry:
        return RedirectResponse(f"/lab/campaigns/{campaign_id}", status_code=303)

    ch = await db.get(CodingChallenge, entry.challenge_id)
    return RedirectResponse(
        f"/lab/challenges/{ch.slug}?campaign_id={campaign_id}", status_code=303
    )


# ── SM-2 review queue ─────────────────────────────────────────────────────────

@router.get("/review", response_class=HTMLResponse)
async def review_queue(request: Request, db: AsyncSession = Depends(get_db)):
    due_rows = (await db.scalars(
        select(ChallengeProgress)
        .where(ChallengeProgress.next_review <= date.today())
        .order_by(ChallengeProgress.next_review)
    )).all()

    challenges = []
    for prog in due_rows:
        ch = await db.get(CodingChallenge, prog.challenge_id)
        if ch:
            challenges.append((ch, prog))

    return templates.TemplateResponse("lab/review.html", {
        "request": request,
        "challenges": challenges,
        "due_count": len(challenges),
    })


# ── Report card ───────────────────────────────────────────────────────────────

@router.get("/report", response_class=HTMLResponse)
async def report_card(request: Request, db: AsyncSession = Depends(get_db)):
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    attempts = (await db.scalars(
        select(CodingAttempt)
        .where(
            CodingAttempt.submitted_at >= since,
            CodingAttempt.status.in_(["passed", "failed", "gave_up"]),
            CodingAttempt.is_practice == False,  # noqa: E712
        )
        .order_by(CodingAttempt.submitted_at.desc())
    )).all()

    total = len(attempts)
    passed = sum(1 for a in attempts if a.status == "passed")
    failed = sum(1 for a in attempts if a.status == "failed")
    gave_up = sum(1 for a in attempts if a.status == "gave_up")
    times = [a.time_spent_seconds for a in attempts if a.time_spent_seconds]
    avg_time = round(sum(times) / len(times)) if times else None

    # Subject breakdown
    subject_stats: dict[str, dict] = {}
    for attempt in attempts:
        ch = await db.get(CodingChallenge, attempt.challenge_id)
        if not ch:
            continue
        s = subject_stats.setdefault(ch.subject, {"passed": 0, "total": 0})
        s["total"] += 1
        if attempt.status == "passed":
            s["passed"] += 1

    return templates.TemplateResponse("lab/report.html", {
        "request": request,
        "total": total,
        "passed": passed,
        "failed": failed,
        "gave_up": gave_up,
        "pass_rate": round(passed / total * 100) if total else 0,
        "avg_time": avg_time,
        "subject_stats": subject_stats,
        "attempts": attempts,
        "since": since,
    })
