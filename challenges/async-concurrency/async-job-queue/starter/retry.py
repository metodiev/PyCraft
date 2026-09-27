"""Retry arithmetic and retryability decisions.

This module owns *policy only*: it never sleeps and never touches the event
loop. It answers two questions — may this failure be retried, and how long
should the caller wait? — and leaves the clock to whoever calls it.

Tests import ``RetryPolicy`` from here.
"""

from __future__ import annotations

import asyncio
import random
from collections.abc import Callable
from typing import Protocol

__all__ = ["RandomLike", "RetryPolicy"]


class RandomLike(Protocol):
    """Anything with ``random()``, i.e. ``random.Random`` and test doubles."""

    def random(self) -> float:
        """Return a float in ``[0, 1]``."""


RetryPredicate = Callable[[BaseException], bool]
RetryOn = RetryPredicate | tuple[type[BaseException], ...] | None


class RetryPolicy:
    """Decides whether a failed attempt is retried and how long to wait.

    >>> policy = RetryPolicy(max_attempts=4, base_delay=0.1, multiplier=2.0)
    >>> [policy.delay_for(attempt) for attempt in (1, 2, 3)]
    [0.1, 0.2, 0.4]

    ``rng`` supplies the jitter randomness: inject one and the delays become
    reproducible, which is the only way a test can pin down jittered backoff.
    """

    def __init__(
        self,
        max_attempts: int = 3,
        *,
        base_delay: float = 0.1,
        multiplier: float = 2.0,
        max_delay: float | None = None,
        jitter: float = 0.0,
        retry_on: RetryOn = None,
        rng: RandomLike | None = None,
    ) -> None:
        # TODO: store the configuration and validate it. Reject a non-positive
        # attempt budget, a negative base delay, a multiplier below 1 (the delay
        # must grow), a negative cap and a jitter fraction outside [0, 1].
        # Default ``rng`` to a private ``random.Random()`` instance — never the
        # module-level functions, which would make jitter untestable.
        raise NotImplementedError("Configure RetryPolicy in __init__")

    def is_retryable(self, exc: BaseException) -> bool:
        """Return whether ``exc`` deserves another attempt.

        With ``retry_on`` unset, everything that is an ordinary ``Exception`` is
        retryable. A tuple means "only these types"; a callable is asked
        directly. ``asyncio.CancelledError`` and non-``Exception``
        ``BaseException``s are never retryable — cancellation is a message to
        the task, not a failure to retry.
        """
        # TODO: decide retryability. Note that a class is callable too, so a
        # plain ``callable(retry_on)`` check would misclassify a tuple.
        raise NotImplementedError("Implement RetryPolicy.is_retryable")

    def should_retry(self, attempt: int, exc: BaseException) -> bool:
        """Return whether attempt number ``attempt`` (1-based) may be retried.

        Raising ``ValueError`` for an attempt below 1 keeps off-by-one bugs loud.
        """
        # TODO: another attempt is allowed only while the budget lasts AND the
        # error itself is retryable.
        raise NotImplementedError("Implement RetryPolicy.should_retry")

    def delay_for(self, attempt: int) -> float:
        """Seconds to wait after attempt ``attempt`` failed.

        The backoff is geometric in the attempt number, jitter scales it
        symmetrically, and the result is never negative and never above
        ``max_delay``. Raising ``ValueError`` for an attempt below 1 keeps
        off-by-one bugs loud.
        """
        # TODO: base * multiplier ** (attempt - 1), then jitter, then the cap.
        # The order of the last two matters: the cap must be applied last, or
        # jitter can push a delay back over the limit.
        raise NotImplementedError("Implement RetryPolicy.delay_for")
