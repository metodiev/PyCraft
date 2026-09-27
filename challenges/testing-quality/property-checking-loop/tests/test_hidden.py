"""Hidden tests — graded on Submit, never shown to the learner."""

import random

import pytest

from solution import Report, check


def test_integer_counterexamples_shrink_to_the_boundary():
    report = check(lambda n: n <= 10, lambda rng: rng.randint(0, 1000), trials=200, seed=1)
    assert report.passed is False
    assert report.counterexample == 11

    lower = check(lambda n: n >= -10, lambda rng: rng.randint(-1000, 0), trials=200, seed=2)
    assert lower.counterexample == -11


def test_shrinking_never_crosses_zero_and_shrinks_toward_it():
    # 0 satisfies the property, so the tightest failing values are +/-1.
    report = check(lambda n: n == 0, lambda rng: rng.randint(1, 1000), trials=200, seed=3)
    assert report.counterexample == 1

    mirrored = check(lambda n: n == 0, lambda rng: rng.randint(-1000, -1), trials=200, seed=4)
    assert mirrored.counterexample == -1


def test_a_failing_zero_is_returned_as_zero():
    # Everything generated fails, and 0 fails too, so 0 is the tightest case.
    report = check(lambda n: n < 0, lambda rng: rng.randint(1, 1000), trials=200, seed=3)
    assert report.counterexample == 0
    assert report.passed is False


def test_shrinking_stays_within_a_bounded_number_of_property_calls():
    calls = []

    def prop(value):
        calls.append(value)
        return value <= 10

    report = check(prop, lambda rng: rng.randint(0, 10**6), trials=200, seed=5)
    assert report.counterexample == 11
    # one call per generated candidate (plus the failing one), then a bisection
    assert len(calls) < 60


def test_non_integer_counterexamples_are_passed_through_unchanged():
    report = check(lambda text: "!" not in text, lambda rng: "x" * rng.randint(0, 5) + "!", trials=20)
    assert report.passed is False
    assert report.counterexample.endswith("!")
    assert set(report.counterexample) == {"x", "!"}


def test_seed_controls_the_generated_sequence():
    def generator(rng):
        return rng.random()

    first = check(lambda value: value > 0.5, generator, trials=20, seed=42)
    second = check(lambda value: value > 0.5, generator, trials=20, seed=42)
    third = check(lambda value: value > 0.5, generator, trials=20, seed=43)
    assert first == second
    assert first.counterexample == second.counterexample
    assert (first.counterexample, first.trials_run) != (third.counterexample, third.trials_run)


def test_report_is_a_value_object_with_the_seed():
    report = Report(passed=True, trials_run=3, seed=11)
    with pytest.raises(Exception):
        report.passed = False
    assert report.seed == 11
    assert Report(True, 3, None, None, 11) == report
    assert bool(Report(False, 1)) is False


def test_trials_edges_and_validation():
    with pytest.raises(ValueError):
        check(lambda n: True, lambda rng: 1, trials=-1)
    empty = check(lambda n: False, lambda rng: 1, trials=0)
    assert empty.passed is True
    assert empty.trials_run == 0
    assert empty.counterexample is None


def test_raising_property_reports_error_text_and_shrinks_with_its_error():
    def prop(value):
        if value > 50:
            raise ValueError("value too large")
        return True

    report = check(prop, lambda rng: rng.randint(0, 1000), trials=100, seed=9)
    assert report.passed is False
    assert report.error == "value too large"
    assert report.counterexample == 51


def test_property_is_called_once_per_generated_candidate_when_it_holds():
    seen = []

    def prop(value):
        seen.append(value)
        return True

    report = check(prop, lambda rng: rng.randint(0, 10), trials=7, seed=0)
    assert report.trials_run == 7
    expected_rng = random.Random(0)
    assert seen == [expected_rng.randint(0, 10) for _ in range(7)]
    assert len(seen) == 7
