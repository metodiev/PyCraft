"""Visible tests."""

from solution import build_prefix_sums, range_sum


def test_prefix_includes_a_leading_zero():
    assert build_prefix_sums([1, 2, 3]) == [0, 1, 3, 6]


def test_empty_input():
    assert build_prefix_sums([]) == [0]


def test_range_sum_over_the_whole_list():
    prefix = build_prefix_sums([1, 2, 3])
    assert range_sum(prefix, 0, 3) == 6
