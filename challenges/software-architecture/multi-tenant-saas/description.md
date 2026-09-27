# Project: Multi-tenant SaaS Backend

**This is a project, not a drill.** It is an architecture exercise wearing a
CRUD costume.

Every multi-tenant system that has ever leaked data leaked it the same way: a
call site forgot its `WHERE tenant_id = ?`. The fix that actually works is not
"be careful" — it is to make the unsafe operation **impossible to express**. In
this project a tenant-scoped store simply has no method that can return another
tenant's rows.

| File | Responsibility |
| ---- | -------------- |
| `tenancy.py` | Tenants, plans, entitlements and quota accounting |
| `repository.py` | Tenant-scoped persistence where cross-tenant reads cannot be expressed |
| `control_plane.py` | The façade: provisioning, seats, quota consumption, audit |

## Your task

### `tenancy.py`

| Name | Contract |
| ---- | -------- |
| `Plan` | Frozen dataclass: `id`, `name`, `seat_limit`, `api_quota`, `features: frozenset[str]` |
| `PLANS` | At least `free`, `pro`, `enterprise`, with increasing limits |
| `Tenant` | Frozen dataclass: `id`, `name`, `plan_id`, `seats: frozenset[str]` |
| `EntitlementError` | Raised when a plan does not include a feature or a quota is exhausted |
| `TenantSettings` | Mutable per-tenant settings; **never** shared between tenants |
| `has_feature(tenant, feature)` | Whether the tenant's plan includes it |
| `assert_feature(tenant, feature)` | Same, or raise `EntitlementError` |
| `seat_count(tenant)` / `can_add_seat(tenant, plan)` | Seat accounting |
| `QuotaLedger` | Per-tenant, per-period counters with `remaining`, `consume` and `reset` |

`QuotaLedger.consume(tenant_id, amount)` must raise `EntitlementError` when the
amount would exceed the quota, and must **not** partially apply. A rejected
consumption leaves the counter untouched.

### `repository.py`

`TenantRepository(tenant_id)` stores rows **for one tenant only**.

| Method | Contract |
| ------ | -------- |
| `add(record_id, payload)` | Insert a row owned by this tenant |
| `get(record_id)` | Return the row, or raise `RecordNotFoundError` |
| `all()` | Return only this tenant's rows |
| `update(record_id, payload)` | Replace the payload |
| `delete(record_id)` | Remove the row |
| `count()` | How many rows this tenant owns |

Two repositories for two different tenants, constructed over the same backing
store, must never observe each other's rows — and neither may expose a method
to read across the boundary. Row ids may collide across tenants and must not
interfere.

`RecordNotFoundError` is raised for a row that exists *for another tenant* just
as it is for one that does not exist at all: from this tenant's point of view
there is no difference, and that is the point.

### `control_plane.py`

| Name | Contract |
| ---- | -------- |
| `ControlPlane` | Provisioning and operations, over a shared backing store |
| `.provision(tenant_id, name, plan_id)` | Create a tenant; reject a duplicate id and an unknown plan |
| `.repo(tenant_id)` | A tenant-scoped repository |
| `.add_seat(tenant_id, user_id)` | Enforce the plan's seat limit; adding an existing seat is a no-op, not an error |
| `.remove_seat(tenant_id, user_id)` | Removing an absent seat is a no-op |
| `.consume_quota(tenant_id, amount)` | Charge the plan's `api_quota` |
| `.audit_log(tenant_id)` | Append-only, ordered list of entries for that tenant |

Every mutating operation appends an audit entry recording the tenant, the
action and the actor. **A failed operation must not be audited.** The audit log
for one tenant must never contain another tenant's entries.

## Examples

```pycon
>>> plane = ControlPlane()
>>> plane.provision("acme", "Acme Inc", "free")
>>> plane.add_seat("acme", "u1")
>>> plane.consume_quota("acme", 5)
>>> [entry.action for entry in plane.audit_log("acme")]
['tenant.provisioned', 'seat.added', 'quota.consumed']
```

## Constraints

- Standard library only.
- `tenancy.py` must not import `repository.py` or `control_plane.py`.
- `repository.py` must not import `control_plane.py`.
- No mutable default shared between tenants or between instances — this is a
  hidden test.
- Money and counters are integers.

## Hints

<details>
<summary>Hint 1 — Make the leak unrepresentable</summary>

A repository constructed with its tenant baked in cannot leak by construction:
there is no parameter a caller could pass to ask for someone else's row. That is
worth more than any amount of code review.

</details>

<details>
<summary>Hint 2 — Row ids are scoped</summary>

Key the backing store by `(tenant_id, record_id)`, not by `record_id`. Otherwise
two tenants both using `"1"` will overwrite each other, which is a data-loss bug
that looks like a lookup bug.

</details>

<details>
<summary>Hint 3 — A failed operation audits nothing</summary>

Validate and mutate first, append the audit entry last. If you append first and
the operation then raises, the log claims something happened that did not.

</details>

<details>
<summary>Hint 4 — Quota consumption is all-or-nothing</summary>

Check `remaining >= amount` before decrementing. Decrementing first and
correcting afterwards leaves a window where the counter is wrong, and hides the
bug behind a compensating write.
</details>
