"""Tenant-scoped persistence.

The central design decision of this project: a :class:`TenantRepository` is
constructed *for one tenant* and has no method that can reach another tenant's
rows. Isolation is therefore structural, not a convention that a future
contributor can forget.

Tests import ``RecordNotFoundError``, ``TenantRepository`` and ``SharedStore``
from here.
"""

from __future__ import annotations

from typing import Any


class RecordNotFoundError(LookupError):
    """Raised when a record does not exist *for this tenant*."""


class SharedStore:
    """The backing storage, shared by every tenant's repository.

    Keys are scoped by tenant so that two tenants using the same record id do
    not collide.
    """

    def __init__(self) -> None:
        self._rows: dict[tuple[str, str], dict[str, Any]] = {}

    def put(self, tenant_id: str, record_id: str, payload: dict[str, Any]) -> None:
        """Store a row for a tenant."""
        # TODO: implement.
        raise NotImplementedError

    def fetch(self, tenant_id: str, record_id: str) -> dict[str, Any] | None:
        """Return a row for a tenant, or ``None``."""
        # TODO: implement.
        raise NotImplementedError

    def remove(self, tenant_id: str, record_id: str) -> None:
        """Delete a row for a tenant."""
        # TODO: implement.
        raise NotImplementedError

    def keys_for(self, tenant_id: str) -> list[str]:
        """Every record id owned by one tenant, sorted."""
        # TODO: implement.
        raise NotImplementedError


class TenantRepository:
    """A view over one tenant's rows."""

    def __init__(self, store: SharedStore, tenant_id: str) -> None:
        self._store = store
        self.tenant_id = tenant_id

    def add(self, record_id: str, payload: dict[str, Any]) -> None:
        """Add a row owned by this tenant."""
        # TODO: implement.
        raise NotImplementedError

    def get(self, record_id: str) -> dict[str, Any]:
        """Return this tenant's row, or raise ``RecordNotFoundError``.

        A row belonging to another tenant is indistinguishable from a missing
        one — leaking which case it is is itself an information disclosure.
        """
        # TODO: implement.
        raise NotImplementedError

    def all(self) -> list[dict[str, Any]]:
        """Every row owned by this tenant, in a stable order."""
        # TODO: implement.
        raise NotImplementedError

    def update(self, record_id: str, payload: dict[str, Any]) -> None:
        """Replace this tenant's row."""
        # TODO: implement.
        raise NotImplementedError

    def delete(self, record_id: str) -> None:
        """Remove this tenant's row, or raise ``RecordNotFoundError``."""
        # TODO: implement.
        raise NotImplementedError

    def count(self) -> int:
        """How many rows this tenant owns."""
        # TODO: implement.
        raise NotImplementedError
