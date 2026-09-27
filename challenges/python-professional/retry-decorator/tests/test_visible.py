"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import retry


def test_returns_the_value_without_retry():
    @retry()
    def ok():
        return 42

    assert ok() == 42


def test_retries_until_the_second_attempt_succeeds():
    calls = []

    @retry(times=3)
    def flaky():
        calls.append(1)
        if len(calls) < 2:
            raise ValueError("not yet")
        return "recovered"

    assert flaky() == "recovered"
    assert len(calls) == 2


def test_raises_when_all_attempts_fail():
    @retry(times=2, exceptions=(ValueError,))
    def doomed():
        raise ValueError("boom")

    with pytest.raises(ValueError):
        doomed()


def test_forwards_arguments():
    @retry(times=3)
    def add(a, b, *, extra=0):
        return a + b + extra

    assert add(1, 2, extra=3) == 6
