"""Idempotency: remembering which units of work are already done.

A leaf module. It knows about keys and expiry, and nothing about channels or
notifications; it must not import ``channels`` or ``fanout``.

Tests import ``DedupeStore`` from here.
"""

from __future__ import annotations

import time
from collections.abc import Callable

__all__ = ["DedupeStore"]

Clock = Callable[[], int]


class DedupeStore:
    """Remembers which work has already been done, for a while.

    Two bounds keep the store honest:

    * ``ttl_ms`` — an entry stops counting once the injected clock has moved
      past its expiry, so an id can legitimately be reused later;
    * ``max_size`` — the store holds at most this many live entries, evicting
      the oldest to make room, so a stream of one-off keys cannot grow it
      without limit.

    An entry expires ``ttl_ms`` after it was first recorded; a repeat hit does
    not extend its life.
    """

    def __init__(
        self,
        *,
        ttl_ms: int = 60_000,
        max_size: int = 1_024,
        clock: Clock | None = None,
    ) -> None:
        if ttl_ms <= 0:
            raise ValueError(f"ttl_ms must be positive, got {ttl_ms}")
        if max_size < 1:
            raise ValueError(f"max_size must be at least 1, got {max_size}")
        self.ttl_ms = int(ttl_ms)
        self.max_size = int(max_size)
        # TODO: store the injected clock and the entries.
        raise NotImplementedError

    def expires_at(self, key: str) -> int | None:
        """When ``key`` stops counting, or ``None`` if it is not held."""
        # TODO: implement.
        raise NotImplementedError

    def is_duplicate(self, key: str) -> bool:
        """Has this key already been recorded, and is that record still live?"""
        # TODO: implement.
        raise NotImplementedError

    def mark(self, key: str) -> bool:
        """Record ``key``; return ``True`` if it was new, ``False`` if it was known."""
        # TODO: implement, enforcing both the TTL and the size bound.
        raise NotImplementedError

    def forget(self, key: str) -> bool:
        """Drop one entry; return whether it was there."""
        # TODO: implement.
        raise NotImplementedError

    def purge_expired(self) -> int:
        """Drop every expired entry and report how many went."""
        # TODO: implement.
        raise NotImplementedError

    def clear(self) -> None:
        """Drop everything."""
        # TODO: implement.
        raise NotImplementedError

    def __len__(self) -> int:
        """How many entries are *live* right now — expired ones do not count."""
        # TODO: implement.
        raise NotImplementedError

    def __contains__(self, key: object) -> bool:
        return isinstance(key, str) and self.is_duplicate(key)
