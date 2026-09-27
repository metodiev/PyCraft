"""Prefix sums for fast range queries."""

from __future__ import annotations

from collections.abc import Sequence


def build_prefix_sums(values: Sequence[int]) -> list[int]:
    """Return prefix sums with a leading zero.

    ``build_prefix_sums([1, 2, 3])`` is ``[0, 1, 3, 6]``.
    """
    # TODO: build the prefix list in one pass.
    raise NotImplementedError


def range_sum(prefix: Sequence[int], start: int, end: int) -> int:
    """Sum of the original values in ``[start, end)``.

    Must run in constant time.
    """
    # TODO: answer from the prefix list alone.
    raise NotImplementedError
