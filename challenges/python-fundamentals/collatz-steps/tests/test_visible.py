"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import collatz_steps, longest_chain


def test_steps_for_small_numbers():
    assert collatz_steps(1) == 0
    assert collatz_steps(2) == 1
    assert collatz_steps(6) == 8


def test_steps_for_twenty_seven():
    assert collatz_steps(27) == 111


def test_returns_an_int():
    assert isinstance(collatz_steps(7), int)


def test_longest_chain_for_small_limits():
    assert longest_chain(1) == 1
    assert longest_chain(6) == 6
    assert longest_chain(10) == 9


def test_invalid_inputs_raise_value_error():
    with pytest.raises(ValueError):
        collatz_steps(0)
    with pytest.raises(ValueError):
        longest_chain(0)
