"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import Countdown, StepRange


def test_step_range_forward_and_backward():
    assert list(StepRange(0, 5, 2)) == [0, 2, 4]
    assert list(StepRange(5, 0, -2)) == [5, 3, 1]
    assert list(StepRange(3, 0)) == []
    assert list(StepRange(0, 5)) == [0, 1, 2, 3, 4]


def test_step_range_is_restartable():
    span = StepRange(0, 4)
    assert list(span) == [0, 1, 2, 3]
    assert list(span) == [0, 1, 2, 3]
    assert iter(span) is not iter(span)


def test_step_range_length_and_repr():
    assert len(StepRange(0, 10, 3)) == 4
    assert len(StepRange(0, 0)) == 0
    assert repr(StepRange(1, 2, 3)) == "StepRange(1, 2, 3)"


def test_countdown_is_single_use():
    counter = Countdown(3)
    assert list(counter) == [3, 2, 1]
    assert list(counter) == []
    assert iter(Countdown(2)) is not None
