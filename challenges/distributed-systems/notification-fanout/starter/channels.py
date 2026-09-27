"""Delivery channels: rate limiting, error classification and circuit breaking.

This module is a leaf: it knows about transports and their failure modes, and
nothing about notifications or orchestration. It must not import ``dedupe`` or
``fanout``.

Every policy here is driven by an **injected clock** — an integer-milliseconds
callable passed in as ``clock`` — never by the wall clock, so tests can move
time by hand.

Tests import the names listed in ``__all__`` from here.
"""

from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

__all__ = [
    "CLOSED",
    "HALF_OPEN",
    "OPEN",
    "Channel",
    "CircuitBreaker",
    "Clock",
    "DeliveryAttempt",
    "DeliveryError",
    "PermanentError",
    "RetryableError",
    "TokenBucket",
    "monotonic_ms",
]

#: The three states of a circuit breaker.
CLOSED = "closed"
OPEN = "open"
HALF_OPEN = "half_open"

#: A clock returns integer milliseconds and only ever moves forward in tests.
Clock = Callable[[], int]


def monotonic_ms() -> int:
    """The default clock: integer milliseconds from ``time.monotonic_ns``."""
    return time.monotonic_ns() // 1_000_000


class DeliveryError(RuntimeError):
    """Base class for a transport refusing or failing a delivery."""


class RetryableError(DeliveryError):
    """A transient failure: the identical attempt may be repeated."""


class PermanentError(DeliveryError):
    """A deterministic failure: repeating it cannot help."""


@dataclass(frozen=True, slots=True)
class DeliveryAttempt:
    """One call into a channel's transport."""

    notification_id: str
    recipient: str
    channel: str
    payload: Any
    idempotency_key: str
    attempt: int


class TokenBucket:
    """A deterministic token bucket.

    ``try_acquire`` succeeds while tokens remain and refuses once they are gone.
    Tokens come back at ``refill_per_second``, in proportion to the time the
    injected clock reports, and never above ``capacity``.
    """

    def __init__(
        self,
        capacity: int,
        refill_per_second: float,
        clock: Clock | None = None,
    ) -> None:
        if capacity < 1:
            raise ValueError(f"capacity must be at least 1, got {capacity}")
        if refill_per_second <= 0:
            raise ValueError(f"refill_per_second must be positive, got {refill_per_second}")
        self.capacity = int(capacity)
        self.refill_per_second = float(refill_per_second)
        self._clock: Clock = clock or monotonic_ms
        # TODO: start full, and remember when the bucket was last refilled.
        raise NotImplementedError

    @property
    def tokens(self) -> float:
        """Tokens available now, refilled according to the injected clock."""
        # TODO: refill for the elapsed time, then report the level.
        raise NotImplementedError

    def try_acquire(self, tokens: int = 1) -> bool:
        """Take ``tokens`` from the bucket, or take nothing and return ``False``."""
        # TODO: refill first, refuse if the bucket is short, otherwise deduct.
        raise NotImplementedError


class CircuitBreaker:
    """Stops calling a channel that keeps failing, and probes it again later.

    The breaker opens after ``failure_threshold`` consecutive *retryable*
    failures and refuses calls while open. It half-opens once ``cooldown_ms``
    of injected time have passed, allowing a single trial call: success closes
    it, a retryable failure re-opens it.
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        cooldown_ms: int = 1_000,
        clock: Clock | None = None,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError(f"failure_threshold must be at least 1, got {failure_threshold}")
        if cooldown_ms < 0:
            raise ValueError(f"cooldown_ms must not be negative, got {cooldown_ms}")
        self.failure_threshold = int(failure_threshold)
        self.cooldown_ms = int(cooldown_ms)
        self._clock: Clock = clock or monotonic_ms
        # TODO: track the state, the consecutive failure run and when it opened.
        raise NotImplementedError

    @property
    def state(self) -> str:
        """``"closed"``, ``"open"`` or ``"half_open"``, as of right now."""
        # TODO: apply the cooldown before reporting.
        raise NotImplementedError

    @property
    def failures(self) -> int:
        """Consecutive retryable failures counted so far."""
        # TODO: report the run length.
        raise NotImplementedError

    def allow(self) -> bool:
        """May a call go out? Claims the single half-open trial when it grants one."""
        # TODO: refuse while open, claim the trial while half-open.
        raise NotImplementedError

    def record_success(self) -> None:
        """A call that worked: close the circuit and forget the failure run."""
        # TODO: implement.
        raise NotImplementedError

    def record_failure(self, *, retryable: bool = True) -> None:
        """Record a failed call. Only retryable failures can open the circuit."""
        # TODO: implement.
        raise NotImplementedError


class Channel:
    """One way of reaching a recipient: a transport plus its policies."""

    def __init__(
        self,
        name: str,
        sender: Callable[[DeliveryAttempt], None],
        *,
        capacity: int = 10,
        refill_per_second: float = 10.0,
        failure_threshold: int = 3,
        cooldown_ms: int = 1_000,
        idempotent: bool = True,
        clock: Clock | None = None,
    ) -> None:
        # TODO: keep the name, the transport and the idempotency flag, and build
        #       this channel's own limiter and breaker over the same clock.
        raise NotImplementedError

    def send(self, attempt: DeliveryAttempt) -> None:
        """Hand one attempt to the transport, which raises on failure."""
        # TODO: call the transport.
        raise NotImplementedError
