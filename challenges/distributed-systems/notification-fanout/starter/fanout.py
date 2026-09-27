"""Orchestration: expand one notification into per-recipient, per-channel deliveries.

This is the entry file. It wires ``channels`` and ``dedupe`` together and owns
the delivery guarantees:

* at-least-once — a unit that failed stays retryable on the next submission;
* no duplicate delivery while a unit is recorded as done;
* an honest report — ``FanoutReport.ok`` must not claim success for a fanout
  that left work unfinished.

Tests import the names listed in ``__all__`` from here.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Any

from channels import Channel, DeliveryAttempt, DeliveryError, PermanentError
from dedupe import DedupeStore

__all__ = [
    "STATUSES",
    "STATUS_CIRCUIT_OPEN",
    "STATUS_DELIVERED",
    "STATUS_DUPLICATE",
    "STATUS_FAILED",
    "STATUS_THROTTLED",
    "Delivery",
    "Fanout",
    "FanoutReport",
    "UnknownChannelError",
    "monotonic_ms",
]

STATUS_DELIVERED = "delivered"
STATUS_DUPLICATE = "duplicate"
STATUS_FAILED = "failed"
STATUS_THROTTLED = "throttled"
STATUS_CIRCUIT_OPEN = "circuit_open"

#: Every status a delivery can end in, in reporting order.
STATUSES: tuple[str, ...] = (
    STATUS_DELIVERED,
    STATUS_DUPLICATE,
    STATUS_FAILED,
    STATUS_THROTTLED,
    STATUS_CIRCUIT_OPEN,
)

#: The only statuses that mean the recipient has (or already had) the message.
OK_STATUSES: frozenset[str] = frozenset({STATUS_DELIVERED, STATUS_DUPLICATE})

Clock = Callable[[], int]


def monotonic_ms() -> int:
    """The default clock: integer milliseconds from ``time.monotonic_ns``."""
    return time.monotonic_ns() // 1_000_000


class UnknownChannelError(KeyError):
    """Raised when a fanout names a channel that was never registered."""


@dataclass(frozen=True, slots=True)
class Delivery:
    """The outcome of one (recipient, channel) unit of a fanout."""

    notification_id: str
    recipient: str
    channel: str
    status: str
    attempts: int = 0
    backoff_ms: int = 0
    error: str | None = None


@dataclass(frozen=True, slots=True)
class FanoutReport:
    """Every delivery one submission produced, plus a verdict on the whole."""

    notification_id: str
    deliveries: tuple[Delivery, ...]

    @property
    def ok(self) -> bool:
        """True only when *every* delivery was delivered or already known."""
        # TODO: a fanout with one failed delivery is not ok.
        raise NotImplementedError

    def by_status(self) -> dict[str, int]:
        """How many deliveries ended in each status. Every status is a key."""
        # TODO: implement.
        raise NotImplementedError

    def for_channel(self, channel: str) -> tuple[Delivery, ...]:
        """The deliveries made over ``channel``."""
        # TODO: implement.
        raise NotImplementedError

    def for_recipient(self, recipient: str) -> tuple[Delivery, ...]:
        """The deliveries made to ``recipient``."""
        # TODO: implement.
        raise NotImplementedError

    @property
    def attempts(self) -> int:
        """How many transport calls this submission cost in total."""
        # TODO: implement.
        raise NotImplementedError


class Fanout:
    """Expands one notification into per-recipient, per-channel deliveries."""

    def __init__(
        self,
        channels: Iterable[Channel] | None = None,
        *,
        clock: Clock | None = None,
        random: "random.Random | None" = None,
        max_attempts: int = 3,
        retry_base_ms: int = 100,
        dedupe_ttl_ms: int = 60_000,
        dedupe_max_size: int = 1_024,
    ) -> None:
        if max_attempts < 1:
            raise ValueError(f"max_attempts must be at least 1, got {max_attempts}")
        if retry_base_ms < 0:
            raise ValueError(f"retry_base_ms must not be negative, got {retry_base_ms}")
        # TODO: keep the clock and RNG (deterministic!), register the channels,
        #       create the dedupe store over the same clock, and zero the stats.
        raise NotImplementedError

    # --- wiring ----------------------------------------------------------
    def register_channel(self, channel: Channel) -> Channel:
        """Make ``channel`` addressable by name. Returns it, so calls chain."""
        # TODO: implement.
        raise NotImplementedError

    def channel(self, name: str) -> Channel:
        """The registered channel called ``name``, or raise ``UnknownChannelError``."""
        # TODO: implement.
        raise NotImplementedError

    # --- keys ------------------------------------------------------------
    @staticmethod
    def unit_key(notification_id: str, channel: str, recipient: str) -> str:
        """The dedupe key of one unit of work: one (notification, channel, recipient)."""
        # TODO: implement.
        raise NotImplementedError

    # --- orchestration ---------------------------------------------------
    def notify(
        self,
        notification_id: str,
        payload: Any = None,
        *,
        recipients: Iterable[str] | str,
        channels: Iterable[str] | str,
    ) -> FanoutReport:
        """Fan ``notification_id`` out to every recipient on every channel.

        Unknown channel names fail the whole submission before anything is sent.
        Submitting an id again retries every unit that is not yet recorded as
        done, and reports the rest as duplicates.
        """
        # TODO: implement. Respect the rate limiter and the circuit breaker,
        #       retry retryable failures only, record finished units in the
        #       dedupe store, and never report an unfinished fanout as ok.
        raise NotImplementedError

    # --- stats -----------------------------------------------------------
    def stats(self) -> dict[str, Any]:
        """Aggregate counters over every submission made so far."""
        # TODO: implement.
        raise NotImplementedError
