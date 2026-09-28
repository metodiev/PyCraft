# Designing Multi-Tenant Systems

A multi-tenant system serves several customers from one deployment, and every design decision downstream follows from one question: how much of the stack is shared? Sharing is what makes the product economically viable; sharing is also what makes one tenant able to affect, or see, another. Everything below is about holding both of those facts at once.

## Three isolation models and what each costs

| Model | Isolation | Operational cost |
| --- | --- | --- |
| Database per tenant | Strongest: no shared connection, no shared schema, no shared credentials | Migration runs N times; connection pools multiply; provisioning is a job |
| Schema per tenant | Strong: namespaced objects, one connection pool per schema | Migrations N times, connection management is fiddly, noisy tenants still share a host |
| Shared schema with a tenant column | Weakest: one missed predicate leaks data | One migration, one pool, cheapest at scale |

The trade is real in both directions. Database-per-tenant gives you the cleanest possible deletion story — drop the database — and the worst fleet-management story: a thousand tenants means a thousand migration targets, and a migration that fails on tenant 631 leaves you with two schema versions in production. Shared schema is trivial to operate and puts the entire burden of correctness on every query.

Most systems land in the middle, or start shared and move the largest tenants onto dedicated infrastructure once their load justifies it. Decide which tier a customer is in during onboarding, not during an incident.

## Tenant identity comes from the session, never from the request

The single largest source of cross-tenant leaks is a `tenant_id` that arrives from the client. It comes from a header, a query parameter, or a request body field, and it is trusted because "only our own frontend calls this".

The rule is absolute: the tenant is resolved from the authenticated context — the token's claims, the session, the host mapping — and the client's opinion about its own identity is discarded.

```python
def resolve_tenant(request: Request) -> str:
    claims = verify_token(request.headers["authorization"])
    tenant_id = claims["tenant_id"]
    if request.query_params.get("tenant_id") not in (None, tenant_id):
        raise PermissionError("tenant mismatch")
    return tenant_id
```

The second half matters as much as the first: an explicit mismatch should be a loud error, not a silent override. Silent overrides hide broken clients that will one day stop sending the parameter at all and be served whatever the default is.

## Defend at every layer, not one

Isolation enforced by discipline fails eventually; enforced by construction fails never. Layer the defences so a single mistake is not a breach.

The query filter is the first layer. Every read and write scoped to the tenant, ideally not by remembering to add `WHERE tenant_id = ?` at each call site but by handing the caller a repository that is already scoped:

```python
class TenantScopedOrders:
    def __init__(self, conn: Connection, tenant_id: str) -> None:
        self._conn, self._tenant = conn, tenant_id

    def open_orders(self) -> list[Order]:
        rows = self._conn.execute(
            "SELECT * FROM orders WHERE tenant_id = ? AND status = 'open'",
            (self._tenant,),
        )
        return [Order(**row) for row in rows]
```

The caller cannot express a query for another tenant because the API has no argument for one. That is the difference between a rule and a mechanism.

The second layer is the unique constraint, and it is the one most teams get wrong. A constraint that is unique in the wrong scope is both a leak vector and a bug:

```text
unique (email)                  -- wrong: two tenants cannot both have ada@x.com
unique (tenant_id, email)       -- right: uniqueness inside the tenant
```

The same applies to slugs, invoice numbers, external ids and idempotency keys. Ask of every unique index: is this uniqueness global because the business says so, or because nobody included the tenant?

The third layer is database row-level security, which applies a predicate in the engine itself, below the application. It is worth the setup cost when several services or ad-hoc SQL reach the same tables, since it protects against the query nobody reviewed. It is not a substitute for a scoped API: a session that forgets to set the tenant variable will see either nothing or everything, depending on how you set the default policy — pick nothing.

## The asymmetry: isolation bugs are silent

An outage announces itself. A cross-tenant leak does not. A missing predicate returns the wrong rows as a successful response with a 200 status, and the only signal is a user noticing something that is not theirs. That asymmetry justifies disproportionate investment — tests that assert a second tenant sees zero rows for every endpoint, and a lint or review rule for raw queries outside the repository layer.

Per-tenant noise is the other silent failure. One customer's backfill saturates the shared connection pool and every other tenant sees latency, with no error anywhere. Per-tenant rate limits, a per-tenant connection budget, and — for the largest customers — separate infrastructure are the containment. Track usage per tenant from day one; you cannot retrofit a fair-share scheduler onto counters you never collected.

## Lifecycle: the part that is easy to forget

Provisioning, migrating, exporting and deleting a tenant are four processes you will run for years.

- Provisioning must be idempotent and repeatable, because it will be re-run after a partial failure.
- Migrations must be online and resumable. Backfills should be chunked per tenant so a failure is limited to one customer's data.
- Export has to be possible per tenant, in a documented format, and within a promise you can meet — data-portability requirements have deadlines attached.
- Deletion must be complete, including backups, caches, search indexes, analytics warehouses and queued events. The tenant's id should be gone from every store; write a test that proves it, because "delete from the primary" is roughly half the work.

Deletion is the strongest argument for a per-tenant data boundary somewhere in your stack: the more isolated the data, the more tractable the delete.

## Practice

[Multi-tenant SaaS Backend](../challenges/software-architecture/multi-tenant-saas) builds exactly this control plane — enforced tenancy at the data layer, plans and entitlements, quota accounting and an audit log. Build it so isolation is enforced by construction, not by the reviewer catching a missing predicate.
