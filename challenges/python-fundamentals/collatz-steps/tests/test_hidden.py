"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import collatz_steps, longest_chain


def test_negative_and_zero_rejected():
    with pytest.raises(ValueError):
        collatz_steps(-3)
    with pytest.raises(ValueError):
        longest_chain(-1)


def test_step_counts_for_a_range():
    expected = {1: 0, 2: 1, 3: 7, 4: 2, 5: 5, 6: 8, 7: 16, 8: 3, 9: 19, 10: 6, 11: 14, 12: 9}
    assert {n: collatz_steps(n) for n in expected} == expected


def test_ties_choose_the_smallest_start():
    # 18 and 19 both take 20 steps; only 18 is the answer.
    assert collatz_steps(18) == collatz_steps(19) == 20
    assert longest_chain(19) == 18


def test_longest_chain_known_values():
    assert longest_chain(2) == 2
    assert longest_chain(3) == 3
    assert longest_chain(20) == 18
    assert longest_chain(100) == 97


def test_longest_chain_is_a_valid_and_maximal_start():
    limit = 2000
    winner = longest_chain(limit)
    assert 1 <= winner <= limit
    best = collatz_steps(winner)
    assert all(collatz_steps(start) <= best for start in range(1, limit + 1))
    smallest_best = min(start for start in range(1, limit + 1) if collatz_steps(start) == best)
    assert winner == smallest_best


def test_even_starts_use_exactly_one_extra_step():
    for n in (2, 4, 8, 16, 32, 64):
        assert collatz_steps(n) == collatz_steps(n // 2) + 1
