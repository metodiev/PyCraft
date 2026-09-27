"""Blast-radius analysis over a dependency graph.

The tests import ``CycleError``, ``critical_path``,
``single_points_of_failure`` and ``transitive_dependents`` from here.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass


class CycleError(ValueError):
    """Raised when the dependency graph contains a cycle."""


def transitive_dependents(graph: Mapping[str, Sequence[str]], component: str) -> list[str]:
    """Everything that stops working when ``component`` fails, sorted.

    The component itself is excluded. Dependencies are transitive: a failure
    propagates along the reverse of the dependency edges.
    """
    # TODO: walk the edges backwards from the failed component.
    raise NotImplementedError


def single_points_of_failure(graph: Mapping[str, Sequence[str]]) -> list[tuple[str, int]]:
    """Every component ranked by blast radius, largest first, ties by name."""
    # TODO: rank all components, including those with no dependents.
    raise NotImplementedError


def critical_path(graph: Mapping[str, Sequence[str]], target: str) -> list[str]:
    """The longest dependency chain ending at ``target``, deepest first.

    Equally long chains are broken lexicographically from the deep end, so the
    answer does not depend on iteration order.
    """
    # TODO: longest path, deterministic tie-break.
    raise NotImplementedError
