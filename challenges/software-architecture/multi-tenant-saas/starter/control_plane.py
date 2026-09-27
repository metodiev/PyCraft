"""The control plane: provisioning, seats, quotas and the audit trail.

This module orchestrates ``tenancy`` and ``repository``. It owns the rule that
matters most for an audit trail: **an operation that fails is not recorded, and
an operation that succeeds is recorded exactly once.**

Tests import ``AuditEntry``, ``ControlPlane`` and ``TenantExistsError`` from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from repository import SharedStore, TenantRepository
from tenancy import EntitlementError, QuotaLedger, Tenant, plan_for


class TenantExistsError(ValueError):
    """Raised when provisioning a tenant id that is already in use."""


@dataclass(frozen=True, slots=True)
class AuditEntry:
    """One recorded action."""

    seq: int
    tenant_id: str
    action: str
    actor: str
    detail: dict[str, Any]


class ControlPlane:
    """Owns tenants, their repositories, their seats, their quota and their log."""

    def __init__(self) -> None:
        # TODO: wire the shared store, per-tenant state and the ledger here.
        raise NotImplementedError

    # --- provisioning ----------------------------------------------------
    def provision(self, tenant_id: str, name: str, plan_id: str) -> Tenant:
        """Create a tenant.

        Rejects a duplicate id (``TenantExistsError``) and an unknown plan
        (``EntitlementError``). A rejected provisioning must not appear in the
        audit log.
        """
        # TODO: implement. Audit last.
        raise NotImplementedError

    def get_tenant(self, tenant_id: str) -> Tenant:
        """Return a tenant, or raise ``KeyError``."""
        # TODO: implement.
        raise NotImplementedError

    def repo(self, tenant_id: str) -> TenantRepository:
        """A repository scoped to ``tenant_id``."""
        # TODO: implement.
        raise NotImplementedError

    # --- seats -----------------------------------------------------------
    def add_seat(self, tenant_id: str, user_id: str, *, actor: str = "system") -> None:
        """Occupy a seat, enforcing the plan's seat limit.

        Adding a seat that already exists is a no-op — and a no-op is not
        audited, because nothing happened.
        """
        # TODO: implement. Audit only on a real change.
        raise NotImplementedError

    def remove_seat(self, tenant_id: str, user_id: str, *, actor: str = "system") -> None:
        """Release a seat. Removing an absent seat is a no-op."""
        # TODO: implement. Audit only on a real change.
        raise NotImplementedError

    # --- quota -----------------------------------------------------------
    def consume_quota(self, tenant_id: str, amount: int, *, actor: str = "system") -> int:
        """Charge the tenant's API quota.

        Returns the new amount used. Raises ``EntitlementError`` when the charge
        would exceed the plan's quota; a rejected charge is not audited and
        leaves the counter untouched.
        """
        # TODO: implement.
        raise NotImplementedError

    def quota_remaining(self, tenant_id: str) -> int:
        """Quota left for the tenant."""
        # TODO: implement.
        raise NotImplementedError

    # --- audit -----------------------------------------------------------
    def audit_log(self, tenant_id: str) -> list[AuditEntry]:
        """This tenant's entries, oldest first.

        Never contains another tenant's entries.
        """
        # TODO: implement.
        raise NotImplementedError
