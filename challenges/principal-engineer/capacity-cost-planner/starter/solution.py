"""Capacity and cost planning for a service fleet.

The tests import ``Fleet``, ``Instance``, ``InsufficientCapacityError``,
``instance_capacity``, ``peak_concurrency``, ``plan_fleet`` and
``months_to_break_even`` from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class InsufficientCapacityError(RuntimeError):
    """Raised when no offered instance type can serve the required peak."""


@dataclass(frozen=True, slots=True)
class Instance:
    """One instance type an operator can buy."""

    name: str
    vcpu: int
    price_per_hour: float


@dataclass(frozen=True, slots=True)
class Fleet:
    """A chosen fleet."""

    instance: str
    count: int
    total_instances: int
    capacity: int
    hourly_cost: float


def instance_capacity(instance: Instance, utilisation: float) -> int:
    """Sustained concurrency one instance serves, floored.

    ``utilisation`` is a fraction in ``(0, 1]``; anything outside raises
    ``ValueError``.
    """
    # TODO: floor(vcpu * utilisation), rejecting an out-of-range utilisation.
    raise NotImplementedError


def peak_concurrency(forecast: Sequence[int], safety_factor: float) -> int:
    """The concurrency the fleet must survive, rounded up.

    An empty forecast raises ``ValueError``. A safety factor below 1 is a
    programming error.
    """
    # TODO: ceil(max(forecast) * safety_factor).
    raise NotImplementedError


def plan_fleet(
    forecast: Sequence[int],
    instances: Sequence[Instance],
    *,
    utilisation: float,
    safety_factor: float,
    failure_domains: int,
) -> Fleet:
    """Choose the cheapest fleet that survives losing a failure domain.

    The chosen type is the one with the lowest price per unit of capacity,
    breaking ties by name. ``count`` is per failure domain, sized so the
    surviving domains still cover the peak.
    """
    # TODO: rank by cost per unit of capacity, size per domain, and total up.
    raise NotImplementedError


def months_to_break_even(monthly_cost: float, upfront_cost: float) -> int:
    """Months until a commitment pays for itself, rounded up.

    A non-positive saving raises ``ValueError`` — it never breaks even.
    """
    # TODO: ceil(upfront / saving).
    raise NotImplementedError
