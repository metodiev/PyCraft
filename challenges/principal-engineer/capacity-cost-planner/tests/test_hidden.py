"""Hidden tests — the judgement calls that separate a plan from a guess."""

import math

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
HUGE = Instance("huge", vcpu=64, price_per_hour=2.00)


# --- survivability: the mistake this challenge exists to catch -----------
def test_a_fleet_survives_losing_one_failure_domain():
    """Sizing for the total instead of the survivors is the classic error."""
    fleet = plan_fleet(
        [1000], [SMALL], utilisation=0.5, safety_factor=1.0, failure_domains=3
    )
    surviving_capacity = fleet.count * (3 - 1) * instance_capacity(SMALL, 0.5)

    assert surviving_capacity >= 1000, f"only {surviving_capacity} survives a domain loss"


def test_sizing_for_the_total_would_be_insufficient():
    """Document the wrong answer explicitly, so the test is self-explaining."""
    peak = 1000
    wrong_total_instances = math.ceil(peak / instance_capacity(SMALL, 0.5))
    wrong_per_domain = math.ceil(wrong_total_instances / 3)
    surviving = wrong_per_domain * 2 * instance_capacity(SMALL, 0.5)

    assert surviving < peak, "this is the failing case the correct plan must avoid"


def test_every_failure_domain_count_survives():
    for domains in (1, 2, 3, 5, 8):
        fleet = plan_fleet(
            [500], [SMALL], utilisation=0.5, safety_factor=1.0, failure_domains=domains
        )
        if domains == 1:
            assert fleet.capacity >= 500
            continue
        assert fleet.count * (domains - 1) * instance_capacity(SMALL, 0.5) >= 500


def test_a_single_failure_domain_has_no_survivors_to_size_for():
    """With one domain there is nothing to lose, so `count` is just enough."""
    fleet = plan_fleet([10], [SMALL], utilisation=0.5, safety_factor=1.0, failure_domains=1)

    assert fleet.count == 10
    assert fleet.total_instances == 10


def test_increasing_failure_domains_increases_the_fleet():
    one = plan_fleet([100], [SMALL], utilisation=0.5, safety_factor=1.0, failure_domains=1)
    three = plan_fleet([100], [SMALL], utilisation=0.5, safety_factor=1.0, failure_domains=3)

    assert three.total_instances >= one.total_instances


# --- capacity arithmetic -------------------------------------------------
def test_capacity_is_floored_not_rounded():
    """3 * 0.5 = 1.5; a fleet cannot lean on half a unit of concurrency."""
    odd = Instance("odd", vcpu=3, price_per_hour=0.10)

    assert instance_capacity(odd, 0.5) == 1


def test_capacity_uses_integer_floats_exactly():
    instance = Instance("exact", vcpu=10, price_per_hour=0.10)

    assert instance_capacity(instance, 0.7) == 7


def test_utilisation_of_one_is_allowed():
    assert instance_capacity(SMALL, 1.0) == 2


def test_a_zero_vcpu_instance_offers_nothing():
    empty = Instance("empty", vcpu=0, price_per_hour=0.01)

    assert instance_capacity(empty, 1.0) == 0


def test_a_negative_utilisation_is_rejected():
    with pytest.raises(ValueError):
        instance_capacity(SMALL, -0.1)


def test_the_peak_is_ceiled_not_truncated():
    assert peak_concurrency([10], 1.05) == 11


def test_the_peak_uses_the_maximum_not_the_mean():
    assert peak_concurrency([1000, 1, 1], 1.0) == 1000


def test_a_safety_factor_below_one_is_rejected():
    with pytest.raises(ValueError):
        peak_concurrency([10], 0.9)


def test_a_zero_forecast_peak_is_zero():
    assert peak_concurrency([0, 0], 1.5) == 0


# --- instance selection --------------------------------------------------
def test_a_zero_capacity_instance_is_never_chosen():
    """A free instance that serves nothing cannot meet any peak."""
    free = Instance("free", vcpu=0, price_per_hour=0.0)

    with pytest.raises(InsufficientCapacityError):
        plan_fleet([1], [free], utilisation=0.5, safety_factor=1.0, failure_domains=1)


def test_the_cheapest_type_wins_against_a_bigger_one():
    fleet = plan_fleet([100], [SMALL, HUGE], utilisation=0.5, safety_factor=1.0, failure_domains=1)

    # small: 0.10/1 = 0.10 per unit; huge: 2.00/32 = 0.0625 per unit.
    assert fleet.instance == "huge"


def test_ties_are_broken_by_name_deterministically():
    alpha = Instance("alpha", vcpu=4, price_per_hour=0.20)
    beta = Instance("beta", vcpu=4, price_per_hour=0.20)

    forward = plan_fleet([4], [alpha, beta], utilisation=0.5, safety_factor=1.0, failure_domains=1)
    reverse = plan_fleet([4], [beta, alpha], utilisation=0.5, safety_factor=1.0, failure_domains=1)

    assert forward.instance == reverse.instance == "alpha"


def test_the_input_instance_list_is_not_mutated():
    offered = [SMALL, LARGE]
    plan_fleet([10], offered, utilisation=0.5, safety_factor=1.0, failure_domains=1)

    assert offered == [SMALL, LARGE]


def test_planning_is_repeatable():
    arguments = ([100, 250], [SMALL, LARGE], 0.6, 1.1, 3)
    first = plan_fleet(
        arguments[0], arguments[1], utilisation=0.6, safety_factor=1.1, failure_domains=3
    )
    second = plan_fleet(
        arguments[0], arguments[1], utilisation=0.6, safety_factor=1.1, failure_domains=3
    )

    assert first == second


def test_a_mixed_workload_still_survives_a_domain_loss():
    fleet = plan_fleet(
        [300, 900, 450], [SMALL, LARGE, HUGE],
        utilisation=0.75, safety_factor=1.3, failure_domains=4,
    )
    peak = peak_concurrency([300, 900, 450], 1.3)
    capacity = instance_capacity(
        {"small": SMALL, "large": LARGE, "huge": HUGE}[fleet.instance], 0.75
    )

    assert fleet.count * 3 * capacity >= peak
    assert fleet.total_instances == fleet.count * 4
    assert fleet.capacity == fleet.total_instances * capacity


def test_the_fleet_totals_are_internally_consistent():
    fleet = plan_fleet([77], [LARGE], utilisation=0.5, safety_factor=1.0, failure_domains=3)

    assert fleet.total_instances == fleet.count * 3
    assert fleet.capacity == fleet.total_instances * instance_capacity(LARGE, 0.5)
    assert fleet.hourly_cost == pytest.approx(fleet.total_instances * LARGE.price_per_hour)


def test_an_instance_that_cannot_be_affordable_is_still_chosen_if_cheapest_per_unit():
    """Cost per unit is the criterion; absolute price is not."""
    cheap_small = Instance("cheap_small", vcpu=1, price_per_hour=0.02)
    pricey_big = Instance("pricey_big", vcpu=100, price_per_hour=5.00)

    fleet = plan_fleet([100], [cheap_small, pricey_big], utilisation=1.0, safety_factor=1.0, failure_domains=1)

    # cheap_small: 0.02 per unit; pricey_big: 0.05 per unit.
    assert fleet.instance == "cheap_small"


# --- break-even ----------------------------------------------------------
def test_break_even_exact_division_is_not_rounded_up_further():
    assert months_to_break_even(monthly_cost=100, upfront_cost=300) == 3


def test_break_even_just_over_a_month_rounds_up():
    assert months_to_break_even(monthly_cost=100, upfront_cost=301) == 4


def test_break_even_fractions_of_a_month_round_up():
    assert months_to_break_even(monthly_cost=325, upfront_cost=1000) == 4


def test_break_even_rejects_a_negative_saving():
    with pytest.raises(ValueError):
        months_to_break_even(monthly_cost=-5, upfront_cost=100)


def test_break_even_of_zero_upfront_is_zero():
    assert months_to_break_even(monthly_cost=100, upfront_cost=0) == 0


def test_break_even_does_not_return_a_float():
    assert isinstance(months_to_break_even(monthly_cost=3, upfront_cost=10), int)


# --- sanity: a plan is what the docs claim -------------------------------
def test_the_returned_object_is_a_fleet():
    fleet = plan_fleet([10], [SMALL], utilisation=0.5, safety_factor=1.0, failure_domains=1)

    assert isinstance(fleet, Fleet)
    assert isinstance(fleet.count, int)
    assert fleet.hourly_cost >= 0
