"""SM-2 spaced repetition algorithm (verbatim from D:/Organiser/drills/engine/sr.py)."""
from datetime import date, timedelta


def review(ease_factor: float | None, interval: int | None, repetitions: int | None, rating: int):
    """
    Apply SM-2 algorithm after a review.

    rating: 0 (fail/blackout) – 5 (perfect recall)
    Returns: (new_ease_factor, new_interval, new_repetitions)

    Intervals:
        rep 0 → 1 day
        rep 1 → 6 days
        rep n → round(prev_interval * ease_factor)

    Failure (rating < 3) resets repetitions and interval to 1.
    """
    ease_factor = ease_factor if ease_factor is not None else 2.5
    interval = interval if interval is not None else 1
    repetitions = repetitions if repetitions is not None else 0

    if rating < 3:
        return ease_factor, 1, 0

    if repetitions == 0:
        new_interval = 1
    elif repetitions == 1:
        new_interval = 6
    else:
        new_interval = round(interval * ease_factor)

    new_ef = ease_factor + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02))
    new_ef = max(1.3, new_ef)

    return new_ef, new_interval, repetitions + 1


def next_due(interval: int) -> date:
    return date.today() + timedelta(days=interval)


def rating_from_attempt(passed: bool, hints_used: int) -> int:
    """Map pass/fail + hint usage to an SM-2 rating (0-5)."""
    if passed:
        if hints_used == 0:
            return 5
        if hints_used == 1:
            return 4
        return 3
    return 0
