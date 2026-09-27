"""Streaks: consecutive days of activity.

A day counts when the learner *solves* something (a graded submission), not
merely when they open the app — the platform rewards demonstrated ability.

A long gap ends the streak. ``longest_streak`` is kept so a learner who lost a
streak can still be rewarded for a past run.
"""

from __future__ import annotations

from datetime import date, timedelta

from app.models import User

# Missing this many consecutive days ends the streak. Two days (rather than one)
# is deliberate: it tolerates a late-night session crossing midnight without
# punishing the learner, while still requiring genuine regularity.
STREAK_GRACE_DAYS = 2


def register_activity(user: User, today: date) -> bool:
    """Record activity for ``today``, returning True when the streak advanced.

    Idempotent: any number of solves on the same day counts as one.

    Reads through ``_value`` because a freshly constructed (unflushed) ``User``
    has ``None`` for columns whose default is applied by the database.
    """
    last = user.last_active_date
    current = _value(user.current_streak)
    longest = _value(user.longest_streak)

    if last is None:
        current = 1
        advanced = True
    elif last == today:
        # Already counted today.
        user.last_active_date = today
        user.current_streak = current or 1
        return False
    elif today - last <= timedelta(days=STREAK_GRACE_DAYS):
        current += 1
        advanced = True
    else:
        # The gap was too long — start over from today.
        current = 1
        advanced = True

    user.current_streak = current
    user.last_active_date = today
    user.longest_streak = max(longest, current)
    return advanced


def _value(raw: int | None) -> int:
    """Treat an unset column default as zero."""
    return 0 if raw is None else int(raw)


def streak_is_alive(user: User, today: date) -> bool:
    """Whether the current streak still counts as active."""
    if user.last_active_date is None or _value(user.current_streak) == 0:
        return False
    return today - user.last_active_date <= timedelta(days=STREAK_GRACE_DAYS)


def effective_streak(user: User, today: date) -> int:
    """Current streak, or 0 if it has lapsed.

    Read-time calculation, so a learner who stopped three weeks ago does not
    keep seeing a stale streak until their next submission.
    """
    return _value(user.current_streak) if streak_is_alive(user, today) else 0
