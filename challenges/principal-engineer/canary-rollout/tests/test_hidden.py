"""Hidden tests — the ordering and accounting details that decide incidents."""

import pytest

from solution import (
    Decision,
    Observation,
    budget_burned,
    decide,
    error_rate,
    run_rollout,
)


def obs(canary_failed: int, baseline_failed: int, total: int = 1000) -> Observation:
    return Observation(canary=[(total, canary_failed)], baseline=[(total, baseline_failed)])


# --- the ordering of the checks ------------------------------------------
def test_the_absolute_ceiling_is_checked_before_the_relative_regression():
    """Both are broken; the ceiling must win, because 'no worse than a bad
    baseline' is not a reason to ship."""
    decision = decide(0.05, obs(90, 88), slo=0.999, max_burn=0.5, threshold=0.05)

    assert decision is Decision.HALT


def test_a_canary_within_the_ceiling_but_worse_than_baseline_rolls_back():
    decision = decide(0.05, obs(40, 20), slo=0.999, max_burn=0.5, threshold=0.5)

    assert decision is Decision.ROLLBACK


def test_a_canary_better_than_baseline_is_promoted():
    decision = decide(0.05, obs(2, 40), slo=0.999, max_burn=0.5, threshold=0.5)

    assert decision is Decision.PROMOTE


def test_regression_exactly_at_the_boundary_is_allowed():
    """The comparison is strictly greater, so equality promotes."""
    decision = decide(0.05, obs(30, 20), slo=0.999, max_burn=0.5, threshold=0.5)

    assert decision is Decision.PROMOTE


def test_the_ceiling_is_strict_so_equality_promotes():
    decision = decide(0.05, obs(50, 10), slo=0.999, max_burn=10.0, threshold=0.05)

    assert decision is Decision.PROMOTE


def test_a_perfect_baseline_still_allows_a_clean_promotion():
    decision = decide(0.05, obs(0, 0), slo=0.999, max_burn=0.5, threshold=0.05)

    assert decision is Decision.PROMOTE


def test_a_regression_from_a_perfect_baseline_rolls_back():
    """A zero baseline makes any failure an infinite relative regression."""
    decision = decide(0.05, obs(1, 0), slo=0.999, max_burn=0.5, threshold=0.5)

    assert decision is Decision.ROLLBACK


def test_a_zero_baseline_within_the_ceiling_does_not_halt():
    decision = decide(0.05, obs(1, 0), slo=0.999, max_burn=0.5, threshold=0.05)

    assert decision is Decision.ROLLBACK


# --- telemetry validation ------------------------------------------------
def test_a_negative_count_is_rejected():
    with pytest.raises(ValueError):
        error_rate([(-1, 0)])


def test_a_negative_failure_count_is_rejected():
    with pytest.raises(ValueError):
        error_rate([(10, -1)])


def test_more_failures_than_requests_is_rejected():
    with pytest.raises(ValueError):
        error_rate([(10, 11)])


def test_impossible_telemetry_is_rejected_inside_decide():
    with pytest.raises(ValueError):
        decide(0.05, Observation(canary=[(10, 11)], baseline=[(10, 0)]), slo=0.999, max_burn=0.5, threshold=0.5)


def test_a_hundred_percent_error_rate_is_representable():
    assert error_rate([(1000, 1000)]) == 1.0


def test_pairs_are_summed_before_dividing_not_averaged():
    """Averaging per-pair rates weights a tiny sample equally with a huge one."""
    # 5/500 = 1%, then 0/5000 = 0%. Correct total is 5/5500, not 0.5%.
    rate = error_rate([(500, 5), (5000, 0)])

    assert rate == pytest.approx(5 / 5500)


# --- budget accounting ---------------------------------------------------
def test_budget_of_a_looser_slo_is_larger():
    strict = budget_burned([(1000, 5)], slo=0.999)
    loose = budget_burned([(1000, 5)], slo=0.99)

    assert strict > loose


def test_no_failures_burns_nothing():
    assert budget_burned([(1000, 0)], slo=0.999) == 0.0


def test_a_loose_slo_rejects_an_impossible_slo():
    with pytest.raises(ValueError):
        budget_burned([(1000, 1)], slo=1.5)


def test_a_negative_slo_is_rejected():
    with pytest.raises(ValueError):
        budget_burned([(1000, 1)], slo=-0.1)


def test_budget_burned_is_rejected_for_impossible_telemetry():
    with pytest.raises(ValueError):
        budget_burned([(10, 11)], slo=0.999)


# --- rollout sequencing ---------------------------------------------------
def test_steps_taken_counts_the_failing_step():
    observations = [obs(0, 0), obs(0, 0), obs(90, 0)]
    rollout = run_rollout(
        [0.01, 0.1, 0.5], observations, slo=0.999, max_burn=0.5, threshold=0.05
    )

    assert rollout.steps_taken == 3
    assert rollout.stage == 0.5


def test_a_single_failing_first_stage_stops_immediately():
    rollout = run_rollout(
        [0.01, 0.1], [obs(90, 0), obs(0, 0)], slo=0.999, max_burn=0.5, threshold=0.05
    )

    assert rollout.steps_taken == 1
    assert rollout.stage == 0.01
    assert rollout.decision is Decision.HALT


def test_the_evidence_of_a_halt_is_preserved():
    """Losing the rates at the moment of failure makes the incident unlearnable."""
    rollout = run_rollout([0.5], [obs(90, 1)], slo=0.999, max_burn=0.5, threshold=0.05)

    assert rollout.canary_error_rate == pytest.approx(0.09)
    assert rollout.baseline_error_rate == pytest.approx(0.001)


def test_a_rollback_records_the_stage_it_stopped_at():
    rollout = run_rollout(
        [0.1, 0.5], [obs(0, 0), obs(40, 20)], slo=0.999, max_burn=0.5, threshold=0.5
    )

    assert rollout.decision is Decision.ROLLBACK
    assert rollout.stage == 0.5
    assert rollout.steps_taken == 2


def test_an_empty_rollout_raises():
    with pytest.raises(ValueError):
        run_rollout([], [], slo=0.999, max_burn=0.5, threshold=0.05)


def test_the_rollout_does_not_mutate_its_inputs():
    observations = [obs(0, 0), obs(1, 0)]
    stages = [0.1, 0.5]
    run_rollout(stages, observations, slo=0.999, max_burn=0.5, threshold=0.5)

    assert stages == [0.1, 0.5]
    assert len(observations) == 2


def test_the_last_stage_promoting_is_reported_as_the_final_stage():
    observations = [obs(0, 0), obs(0, 0)]
    rollout = run_rollout([0.1, 1.0], observations, slo=0.999, max_burn=0.5, threshold=0.05)

    assert rollout.stage == 1.0
    assert rollout.decision is Decision.PROMOTE
    assert rollout.steps_taken == 2


def test_a_healthy_rollout_reports_the_rates_of_its_last_stage():
    observations = [
        Observation(canary=[(1000, 1)], baseline=[(1000, 1)]),
        Observation(canary=[(1000, 3)], baseline=[(1000, 1)]),
    ]
    rollout = run_rollout([0.1, 1.0], observations, slo=0.999, max_burn=0.5, threshold=0.05)

    assert rollout.canary_error_rate == pytest.approx(0.003)


def test_equal_length_stages_and_observations_of_one_are_allowed():
    rollout = run_rollout([0.05], [obs(0, 0)], slo=0.999, max_burn=0.5, threshold=0.05)

    assert rollout.steps_taken == 1
