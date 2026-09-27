"""Model Docker build-cache invalidation.

The tests import ``BuildCost``, ``DockerfileError``, ``Instruction``,
``cache_miss_index``, ``parse_dockerfile``, ``rebuild_cost`` and
``suggest_reorder`` from here.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


class DockerfileError(ValueError):
    """Raised when a line is not a valid ``KEYWORD rest`` instruction."""


@dataclass(frozen=True, slots=True)
class Instruction:
    """One Dockerfile instruction."""

    keyword: str
    argument: str


@dataclass(frozen=True, slots=True)
class BuildCost:
    """What a change costs the build."""

    misses: int
    rebuilds: int
    skipped: int
    ratio: float


def parse_dockerfile(text: str) -> list[Instruction]:
    """Parse a Dockerfile subset into instructions, in order.

    Joins backslash continuations and collapses whitespace inside an argument,
    so an identical instruction always renders identically.
    """
    # TODO: join continuations, skip blanks and comments, upper-case keywords.
    raise NotImplementedError


def cache_miss_index(
    instructions: Sequence[Instruction], changed: set[str]
) -> int | None:
    """Index of the first instruction that misses the cache, or ``None``.

    Once a layer misses, every later layer misses too.
    """
    # TODO: walk in order, tracking whether an earlier layer already missed.
    raise NotImplementedError


def rebuild_cost(instructions: Sequence[Instruction], changed: set[str]) -> BuildCost:
    """How many layers rebuild and how much cache survives."""
    # TODO: derive from the first miss.
    raise NotImplementedError


def suggest_reorder(instructions: Sequence[Instruction]) -> list[Instruction]:
    """Move whole-context copies after the ``RUN`` layers.

    Preserves the relative order of everything else, and does not mutate the
    input.
    """
    # TODO: partition and reassemble.
    raise NotImplementedError
