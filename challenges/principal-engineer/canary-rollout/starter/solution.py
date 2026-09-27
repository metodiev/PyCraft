"""Progressive rollout driven by error budgets.

The tests import ``Decision``, ``Observation``, ``Rollout``, ``budget_burned``,
``decide``, ``error_rate`` and ``run_rollout`` from here.
"""

from __future__ import annotations

import enum
from collections.abc import Sequence
from dataclasses import dataclass


class Decision(enum.StrEnum):
    """What to do with the canary at this stage."""

    PROMOTE = "promote"
    ROLLBACK = "rollback"
    HALT = "halt"


@dataclass(frozen=True, slots=True)
class Observation:
    """Telemetry for one rollout step: the canary against the baseline."""

    canary: list[tuple[int, int]]
    baseline: list[tuple[int, int]]


@dataclass(frozen=True, slots=True)
class Rollout:
    """The outcome of a rollout sequence."""

    stage: float
    decision: Decision
    canary_error_rate: float
    baseline_error_rate: float
    steps_taken: int


def error_rate(observations: Sequence[tuple[int, int]]) -> float:
    """Fraction of requests that failed, over ``(total, failed)`` pairs.

    An empty list or a zero total is ``0.0``. Impossible telemetry raises
    ``ValueError`` rather than being averaged away.
    """
    # TODO: validate the pairs, then divide.
    raise NotImplementedError


def budget_burned(observations: Sequence[tuple[int, int]], slo: float) -> float:
    """Fraction of the error budget consumed.

    ``1.0`` means the budget is exactly used up. An SLO of ``1.0`` leaves no
    budget at all and raises ``ValueError``.
    """
    # TODO: budget = (1 - slo) * total; burned = failed / budget.
    raise NotImplementedError


def decide(
    stage: float,
    observations: Observation,
    *,
    slo: float,
    max_burn: float,
    threshold: float,
) -> Decision:
    """Decide whether to promote, roll back or halt.

    The absolute ``threshold`` is evaluated before the relative ``max_burn``
    comparison.
    """
    # TODO: implement the ordered checks.
    raise NotImplementedError


def run_rollout(
    stages: Sequence[float],
    observations: Sequence[Observation],
    *,
    slo: float,
    max_burn: float,
    threshold: float,
) -> Rollout:
    """Walk the stages and stop at the first non-promote."""
    # TODO: decide each stage in order, record the evidence, stop on failure.
    raise NotImplementedError
