"""Tenants, plans, entitlements and quota accounting.

This module owns the *commercial* rules: what a plan allows and how much of it a
tenant has used. It knows nothing about storage or orchestration, and must not
import ``repository`` or ``control_plane``.

Tests import the names listed in ``__all__`` from here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

__all__ = [
    "EntitlementError",
    "PLANS",
    "Plan",
    "QuotaLedger",
    "Tenant",
    "TenantSettings",
    "assert_feature",
    "can_add_seat",
    "has_feature",
    "plan_for",
    "seat_count",
]


class EntitlementError(PermissionError):
    """Raised when a plan does not include a feature, or a quota is exhausted."""


@dataclass(frozen=True, slots=True)
class Plan:
    """What a tenant on this plan is allowed to do."""

    id: str
    name: str
    seat_limit: int
    api_quota: int
    features: frozenset[str]


#: Ordered least to most capable.
PLANS: dict[str, Plan] = {
    "free": Plan("free", "Free", seat_limit=1, api_quota=1_000, features=frozenset({"core"})),
    "pro": Plan(
        "pro",
        "Pro",
        seat_limit=25,
        api_quota=50_000,
        features=frozenset({"core", "api", "webhooks"}),
    ),
    "enterprise": Plan(
        "enterprise",
        "Enterprise",
        seat_limit=1_000,
        api_quota=1_000_000,
        features=frozenset({"core", "api", "webhooks", "sso", "audit"}),
    ),
}


@dataclass(frozen=True, slots=True)
class Tenant:
    """One customer organisation.

    ``seats`` holds the ids of users occupying a seat on this tenant's plan.
    """

    id: str
    name: str
    plan_id: str
    seats: frozenset[str] = frozenset()

    def with_seat(self, user_id: str) -> Tenant:
        """Return a copy with ``user_id`` occupying a seat."""
        # TODO: implement immutably — a frozen dataclass cannot be mutated, so
        # return a new instance. Adding an existing seat must be a no-op.
        raise NotImplementedError

    def without_seat(self, user_id: str) -> Tenant:
        """Return a copy with ``user_id``'s seat released."""
        # TODO: implement immutably. Removing an absent seat is a no-op.
        raise NotImplementedError


@dataclass
class TenantSettings:
    """Mutable per-tenant configuration.

    Note the absence of a class-level mutable default: sharing one dict between
    tenants is the classic way to leak configuration across customers.
    """

    values: dict[str, Any] = field(default_factory=dict)

    def set(self, key: str, value: Any) -> None:
        """Set one setting."""
        # TODO: implement.
        raise NotImplementedError

    def get(self, key: str, default: Any = None) -> Any:
        """Read one setting."""
        # TODO: implement.
        raise NotImplementedError


def plan_for(plan_id: str) -> Plan:
    """Return the plan, or raise ``EntitlementError`` for an unknown id."""
    # TODO: implement.
    raise NotImplementedError


def has_feature(tenant: Tenant, feature: str) -> bool:
    """Whether the tenant's plan includes ``feature``."""
    # TODO: implement.
    raise NotImplementedError


def assert_feature(tenant: Tenant, feature: str) -> None:
    """Raise ``EntitlementError`` unless the tenant's plan includes ``feature``."""
    # TODO: implement.
    raise NotImplementedError


def seat_count(tenant: Tenant) -> int:
    """How many seats the tenant currently occupies."""
    # TODO: implement.
    raise NotImplementedError


def can_add_seat(tenant: Tenant, plan: Plan) -> bool:
    """Whether one more seat fits within the plan."""
    # TODO: implement.
    raise NotImplementedError


class QuotaLedger:
    """Per-tenant, per-period counters.

    Consumption is all-or-nothing: a rejected request must leave the counter
    exactly as it was.
    """

    def __init__(self) -> None:
        self._used: dict[str, int] = {}

    def used(self, tenant_id: str) -> int:
        """Amount consumed in the current period."""
        # TODO: implement.
        raise NotImplementedError

    def remaining(self, tenant_id: str, quota: int) -> int:
        """Quota left in the current period. Never negative."""
        # TODO: implement.
        raise NotImplementedError

    def consume(self, tenant_id: str, amount: int, quota: int) -> int:
        """Charge ``amount`` against ``quota``.

        Returns the new amount used. Raises ``EntitlementError`` when the charge
        would exceed the quota, without changing anything. A non-positive
        ``amount`` is a programming error.
        """
        # TODO: check first, then mutate.
        raise NotImplementedError

    def reset(self, tenant_id: str) -> None:
        """Start a new period for one tenant."""
        # TODO: implement.
        raise NotImplementedError
