"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import Report, check


def test_passing_property_reports_success():
    report = check(lambda n: n <= n, lambda rng: rng.randint(0, 10), trials=25)
    assert report.passed
    assert report.trials_run == 25
    assert report.counterexample is None
    assert report.error is None
    assert bool(report) is True


def test_failing_property_reports_a_counterexample():
    report = check(lambda n: n < 5, lambda rng: rng.randint(0, 100), trials=50, seed=3)
    assert report.passed is False
    assert report.counterexample is not None
    assert report.counterexample >= 5


def test_same_seed_gives_the_same_report():
    args = (lambda n: n < 100, lambda rng: rng.randint(0, 1000))
    assert check(*args, trials=30, seed=7) == check(*args, trials=30, seed=7)
    assert isinstance(check(*args, trials=1, seed=7), Report)


def test_exceptions_become_failures():
    def explode(value):
        raise ZeroDivisionError("division by zero")

    report = check(explode, lambda rng: rng.randint(1, 5), trials=5)
    assert report.passed is False
    assert report.error == "division by zero"
