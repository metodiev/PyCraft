"""Visible tests — the learner sees these before submitting."""

import pytest

from solution import (
    Fleet,
    Instance,
    InsufficientCapacityError,
    instance_capacity,
    months_to_break_even,
    peak_concurrency,
    plan_fleet,
)

SMALL = Instance("small", vcpu=2, price_per_hour=0.10)
LARGE = Instance("large", vcpu=16, price_per_hour=0.40)


def test_instance_capacity_floors_the_product():
    assert instance_capacity(SMALL, 0.5) == 1


def test_instance_capacity_rejects_an_out_of_range_utilisation():
    with pytest.raises(ValueError):
        instance_capacity(SMALL, 0)
    with pytest.raises(ValueError):
        instance_capacity(SMALL, 1.5)


def test_peak_concurrency_multiplies_the_maximum():
    assert peak_concurrency([100, 250, 180], 1.2) == 300


def test_peak_concurrency_rounds_up():
    assert peak_concurrency([10], 1.15) == 12


def test_peak_concurrency_rejects_an_empty_forecast():
    with pytest.raises(ValueError):
        peak_concurrency([], 1.0)


def test_an_empty_load_needs_no_instances():
    fleet = plan_fleet([0], [SMALL], utilisation=0.5, safety_factor=1.0, failure_domains=3)

    assert fleet.total_instances == 0
    assert fleet.hourly_cost == 0


def test_plan_fleet_with_one_failure_domain_sizes_for_the_peak():
    """With a single domain there is nothing to lose, so the peak is the target."""
    fleet = plan_fleet(
        [100, 250, 180], [SMALL], utilisation=0.5, safety_factor=1.2, failure_domains=1
    )

    assert fleet == Fleet(
        instance="small", count=300, total_instances=300, capacity=300, hourly_cost=30.0
    )


def test_plan_fleet_prefers_the_cheapest_per_unit():
    # small: 0.10 per unit; large: 0.40 / 8 = 0.05 per unit.
    fleet = plan_fleet([16], [SMALL, LARGE], utilisation=0.5, safety_factor=1.0, failure_domains=1)

    assert fleet.instance == "large"


def test_plan_fleet_raises_when_no_instance_offers_capacity():
    """Sizing up can reach any peak; serving *nothing* is the real dead end."""
    empty = Instance("empty", vcpu=0, price_per_hour=0.01)

    with pytest.raises(InsufficientCapacityError):
        plan_fleet([10_000], [empty], utilisation=0.5, safety_factor=1.0, failure_domains=1)


def test_break_even_rounds_up():
    assert months_to_break_even(monthly_cost=100, upfront_cost=250) == 3


def test_break_even_rejects_a_non_positive_saving():
    with pytest.raises(ValueError):
        months_to_break_even(monthly_cost=0, upfront_cost=100)
