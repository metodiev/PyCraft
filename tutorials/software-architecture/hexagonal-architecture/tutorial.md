# Ports and Adapters: Keeping the Domain Clean

Hexagonal architecture is often drawn as a hexagon and explained with a diagram of boxes. The diagram is not the idea. The idea is a dependency rule: the domain in the centre is written in terms of its own concepts and knows nothing about HTTP, SQL or the clock, and everything else depends on it.

## What "the domain knows nothing" means concretely

A `PricingService` that constructs an `httpx.Client`, reads `os.environ`, or calls `datetime.now()` in the middle of a discount calculation has three invisible inputs. Tests must patch them, a library upgrade breaks business logic, and no one can answer "what does this price depend on?" without reading the whole file.

Ports and adapters remove those hidden inputs by pushing them to the edge and inverting the direction of the import.

```python
# domain/pricing.py — owns the port, defines what it needs
from datetime import date
from decimal import Decimal
from typing import Protocol

class Clock(Protocol):
    def today(self) -> date: ...

class FxRates(Protocol):
    def rate(self, frm: str, to: str) -> Decimal: ...

class PricingService:
    def __init__(self, clock: Clock, rates: FxRates) -> None:
        self._clock = clock
        self._rates = rates
```

Both protocols express domain vocabulary. Neither mentions a library. The domain defines the interface and the adapter satisfies it, which is the inversion: in a layered design the domain imports the database package; here the database adapter imports the domain.

## Adapters are replaceable by construction

An adapter is a thin class that implements a port with a real technology. Because it implements a protocol the domain already declared, it can be swapped without touching the centre.

```python
# adapters/fx.py
class EcbFxRates:
    """Daily reference rates published by the ECB, cached for the day."""
    def __init__(self, client: HttpClient, clock: Clock) -> None: ...
    def rate(self, frm: str, to: str) -> Decimal: ...
```

In production this calls an HTTP client. In tests it is a dictionary.

```python
class FixedRates:
    def __init__(self, table: dict[tuple[str, str], str]) -> None:
        self._table = table
    def rate(self, frm: str, to: str) -> Decimal:
        return Decimal(self._table[(frm, to)])
```

A pricing test can now assert exact arithmetic across a currency boundary with no network, no fixture server, and no patching — and it runs in microseconds. That is the practical payoff: the domain's test suite expresses business rules instead of mocking a transport.

Note what makes the fake trustworthy: the fake is written against the same protocol, so the type checker flags a drift in the signature. Keep a small contract test that runs the same assertions against the real adapter, gated behind a marker, so the fake cannot drift semantically in silence.

## Where the ports actually go

The common failure is a port shaped like the technology it hides. If `OrderRepository` has `execute(sql, params)`, the domain is still coupled to SQL — just with an extra name in between. Ports should be expressed as the operations the domain performs, not as the calls the driver supports:

| Coupled port | Honest port |
| --- | --- |
| `find_by_sql(query)` | `orders_for_customer(customer_id)` |
| `send(payload, topic)` | `order_placed(order)` |
| `get(url, headers)` | `current_rate(from_ccy, to_ccy)` |

The same discipline applies to reads: if a screen needs a denormalised view, define a read port that returns the view the screen needs rather than reusing the write-side repository. Two ports over one table is normal and honest.

## The honest counter-argument

Hexagonal architecture costs indirection. For a small CRUD service with one screen, one table and no rules, the ports are a second copy of the schema in Protocol form, and the adapters are pass-through call sites. The domain will never be tested without I/O because there is nothing to test that is not I/O. In that codebase, a query in the route handler is not a sin — it is a shorter path to the same behaviour, and the abstraction will slow every change.

Skip the ceremony when the logic is trivial and the storage is not expected to change. Adopt it when the domain has rules worth testing without infrastructure, when the same logic must serve a second caller (a batch job, a CLI, a second protocol), or when the storage engine, vendor or clock is genuinely expected to move. Those three are the actual triggers; "it is good practice" is not one.

## Practice

[Multi-tenant SaaS Backend](../challenges/software-architecture/multi-tenant-saas) asks for isolation enforced by construction. A tenant-scoped repository port is a textbook case: the domain states that every query is for one tenant, and the adapter cannot be asked for another's rows.
