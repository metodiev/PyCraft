"""The per-submission memory ceiling.

A single submission must not be able to harm the sandbox host or the API
container, so every challenge's ``memory_limit_mb`` is clamped to
``max_memory_limit_mb``. These tests pin that ceiling and the two coupled
details that make it meaningful:

* the clamp is applied by ``ExecutionLimits.clamped`` (the only thing that
  reaches ``docker run --memory``), and
* the API reports the *clamped* value, so the workspace never advertises a
  budget the sandbox will not grant.
"""

from __future__ import annotations

import pytest
from app.core.config import Settings
from app.execution.models import ExecutionLimits

#: The product decision under test: no submission may exceed 100 MB.
MEMORY_CAP_MB = 100

#: CPython plus pytest need roughly this much before learner code runs.
INTERPRETER_FLOOR_MB = 33


def _clamped(memory_limit_mb: int, *, ceiling: int = MEMORY_CAP_MB) -> int:
    limits = ExecutionLimits(time_limit_ms=5_000, memory_limit_mb=memory_limit_mb)
    return limits.clamped(max_time_ms=10_000, max_memory_mb=ceiling).memory_limit_mb


def test_configured_ceiling_is_the_product_cap() -> None:
    settings = Settings()
    assert settings.max_memory_limit_mb == MEMORY_CAP_MB
    # The default for challenges that declare nothing must not exceed the cap,
    # or an unconfigured challenge would silently ask for more than it gets.
    assert settings.default_memory_limit_mb <= settings.max_memory_limit_mb


@pytest.mark.parametrize("declared", [128, 256, 512, 1024, 1_000_000])
def test_limits_above_the_cap_are_clamped_down(declared: int) -> None:
    """Every challenge in the catalogue currently declares 128 or 256 MB."""
    assert _clamped(declared) == MEMORY_CAP_MB


@pytest.mark.parametrize("declared", [32, 64, 99, 100])
def test_limits_at_or_below_the_cap_are_untouched(declared: int) -> None:
    """A challenge may still choose a *tighter* budget for its own code."""
    assert _clamped(declared) == declared


def test_the_cap_leaves_room_above_the_interpreter_floor() -> None:
    """The cap must not be so tight that ordinary submissions fail.

    Measured on the real catalogue: CPython plus pytest alone need ~33 MB, and
    the heaviest suite peaks near 46 MB. A cap at or below the floor would turn
    the platform's own startup cost into a memory failure.
    """
    assert MEMORY_CAP_MB > INTERPRETER_FLOOR_MB * 2
