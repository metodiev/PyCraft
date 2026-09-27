"""Hidden tests — graded on Submit, never shown to the learner."""

import pytest

from solution import Countdown, StepRange


def test_len_is_exact_for_negative_steps():
    assert len(StepRange(11, 0, -3)) == 4
    assert len(StepRange(0, -10, -1)) == 10
    assert len(StepRange(0, -10)) == 0
    assert len(StepRange(-4, 6, 2)) == 5
    assert [len(StepRange(0, n, 7)) for n in (0, 1, 6, 7, 14)] == [0, 1, 1, 1, 2]


def test_contains_uses_the_sequence_not_a_formula():
    span = StepRange(0, 10, 3)          # 0, 3, 6, 9
    assert 6 in span
    assert 7 not in span
    assert 9 in span
    assert 10 not in span
    assert 1 not in span
    assert 0 in StepRange(0, 3)


def test_equality_compares_sequences():
    assert StepRange(0, 5, 1) == StepRange(0, 5)
    assert StepRange(0, 5, 2) != StepRange(0, 5, 3)
    assert StepRange(3, 0) == StepRange(0, 0)
    assert StepRange(0, 5) != "01234"


def test_validation_rejects_booleans_and_zero_step():
    with pytest.raises(ValueError):
        StepRange(0, 5, 0)
    with pytest.raises(ValueError):
        StepRange(True, 5)
    with pytest.raises(ValueError):
        StepRange(0, 5, 1.0)
    with pytest.raises(ValueError):
        Countdown(-1)
    with pytest.raises(ValueError):
        Countdown(True)


def test_attributes_are_read_only():
    span = StepRange(0, 5)
    with pytest.raises(AttributeError):
        span.start = 9
    with pytest.raises(AttributeError):
        span.step = 2
    assert span.start == 0 and span.stop == 5 and span.step == 1


def test_countdown_exhaustion_and_direct_dunder_calls():
    counter = Countdown(2)
    assert counter.__next__() == 2
    assert next(counter) == 1
    with pytest.raises(StopIteration) as first:
        next(counter)
    assert str(first.value) == ""
    with pytest.raises(StopIteration):
        next(counter)
    assert list(Countdown(0)) == []


def test_nested_iteration_over_one_step_range():
    span = StepRange(0, 3)
    pairs = [(a, b) for a in span for b in span]
    assert len(pairs) == 9
    assert pairs[0] == (0, 0)
    assert pairs[-1] == (2, 2)
    assert list(span) == [0, 1, 2]
