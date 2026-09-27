"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import (
    Decision,
    Observation,
    Rollout,
    budget_burned,
    decide,
    error_rate,
    run_rollout,
)


def test_error_rate_is_failed_over_total():
    assert error_rate([(1000, 10)]) == 0.01


def test_error_rate_sums_across_pairs():
    assert error_rate([(500, 5), (500, 5)]) == 0.01


def test_error_rate_of_no_requests_is_zero():
    assert error_rate([]) == 0.0
    assert error_rate([(0, 0)]) == 0.0


def test_error_rate_rejects_impossible_telemetry():
    with pytest.raises(ValueError):
        error_rate([(10, 20)])


def test_budget_burned_is_a_fraction_of_the_budget():
    # 99.9% SLO over 1000 requests allows exactly 1 failure. Compared with a
    # tolerance because (1 - 0.999) is not exactly 0.001 in binary floating point.
    assert budget_burned([(1000, 1)], slo=0.999) == pytest.approx(1.0)


def test_budget_burned_above_one_means_over_budget():
    assert budget_burned([(1000, 2)], slo=0.999) == pytest.approx(2.0)


def test_budget_burned_rejects_a_full_slo():
    with pytest.raises(ValueError):
        budget_burned([(1000, 1)], slo=1.0)


def test_a_clean_canary_is_promoted():
    decision = decide(
        0.05,
        Observation(canary=[(1000, 2)], baseline=[(1000, 2)]),
        slo=0.999,
        max_burn=0.5,
        threshold=0.05,
    )

    assert decision is Decision.PROMOTE


def test_an_absolute_breach_halts():
    decision = decide(
        0.05,
        Observation(canary=[(1000, 90)], baseline=[(1000, 80)]),
        slo=0.999,
        max_burn=0.5,
        threshold=0.05,
    )

    assert decision is Decision.HALT


def test_a_relative_regression_rolls_back():
    decision = decide(
        0.05,
        Observation(canary=[(1000, 40)], baseline=[(1000, 20)]),
        slo=0.999,
        max_burn=0.5,
        threshold=0.5,
    )

    assert decision is Decision.ROLLBACK


def test_a_rollout_that_stays_healthy_promotes_everywhere():
    observations = [
        Observation(canary=[(1000, 1)], baseline=[(1000, 1)]),
        Observation(canary=[(1000, 1)], baseline=[(1000, 1)]),
    ]

    rollout = run_rollout([0.05, 0.5], observations, slo=0.999, max_burn=0.5, threshold=0.05)

    assert rollout == Rollout(
        stage=0.5,
        decision=Decision.PROMOTE,
        canary_error_rate=0.001,
        baseline_error_rate=0.001,
        steps_taken=2,
    )


def test_a_rollout_stops_at_the_failing_stage():
    observations = [
        Observation(canary=[(1000, 1)], baseline=[(1000, 1)]),
        Observation(canary=[(1000, 90)], baseline=[(1000, 20)]),
        Observation(canary=[(1000, 1)], baseline=[(1000, 1)]),
    ]

    rollout = run_rollout(
        [0.05, 0.5, 1.0], observations, slo=0.999, max_burn=0.5, threshold=0.5
    )

    assert rollout.decision is Decision.ROLLBACK
    assert rollout.stage == 0.5
    assert rollout.steps_taken == 2


def test_a_length_mismatch_is_rejected():
    with pytest.raises(ValueError):
        run_rollout(
            [0.05, 0.5],
            [Observation(canary=[(1, 0)], baseline=[(1, 0)])],
            slo=0.999,
            max_burn=0.5,
            threshold=0.05,
        )
