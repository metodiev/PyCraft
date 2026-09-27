"""Hidden tests - the complexity contract and the edge cases."""

import time

from solution import build_prefix_sums, range_sum


def test_range_sum_is_constant_time_not_a_rescan():
    """Recomputing the sum per query is the naive solution this catches.

    The reference answers 1000 queries in well under a millisecond; a rescan
    needs tens of seconds. The bound sits far from both, so it is not flaky on
    a slow machine while still failing any O(n) implementation.
    """
    values = list(range(100_000))
    prefix = build_prefix_sums(values)

    started = time.perf_counter()
    for _ in range(1000):
        range_sum(prefix, 10, 90_000)
    elapsed = time.perf_counter() - started

    assert elapsed < 0.5, f"1000 queries took {elapsed:.2f}s; range_sum is rescanning"


def test_range_sum_matches_a_manual_sum_across_all_boundaries():
    values = [5, -3, 8, 0, 12]
    prefix = build_prefix_sums(values)

    for start in range(len(values) + 1):
        for end in range(start, len(values) + 1):
            assert range_sum(prefix, start, end) == sum(values[start:end])


def test_an_empty_range_is_zero():
    prefix = build_prefix_sums([1, 2, 3])
    assert range_sum(prefix, 2, 2) == 0


def test_negative_values_are_handled():
    prefix = build_prefix_sums([-5, 10, -20])
    assert range_sum(prefix, 1, 3) == -10


def test_prefix_matches_a_manual_accumulation():
    values = [3, 1, 4, 1, 5, 9, 2, 6]
    prefix = build_prefix_sums(values)

    running = 0
    for index, value in enumerate(values, start=1):
        running += value
        assert prefix[index] == running


def test_a_long_list_builds_in_one_pass():
    values = list(range(100_000))
    prefix = build_prefix_sums(values)

    assert len(prefix) == 100_001
    assert prefix[-1] == sum(values)
