# Layering a Service: Routing, Domain and Assembly

A handler that parses the request, applies business rules and writes to the
database is not layered — it is one function wearing three hats. Each layer
exists so a decision can be tested, changed and reasoned about without dragging
the rest of the system along.

## Three jobs, three layers

| Layer | Responsible for | Must never |
| ----- | --------------- | ---------- |
| Routing / transport | Parsing input, validating shape, calling the domain, serialising output, choosing status codes | Contain business rules or reach into the database |
| Domain | Decisions, invariants, calculations over domain values | Import the framework, touch request or response objects, read environment variables |
| Assembly | Constructing objects, choosing implementations, owning lifetimes | Handle requests or decide anything |

The test is mechanical. If you cannot exercise a rule from a plain Python
interpreter, it is not in the domain layer. If a route function contains an `if`
that depends on the *meaning* of the data rather than its shape, that branch
belongs one layer down.

## Dependency inversion in practice

The domain must not import the framework, and it must not import the database
client either. It declares the interface it needs; the edge supplies the
implementation.

```python
from typing import Protocol


class PriceBook(Protocol):
    def price_of(self, sku: str) -> int: ...


class QuoteService:
    def __init__(self, prices: PriceBook) -> None:
        self._prices = prices

    def quote(self, sku: str, quantity: int) -> int:
        if quantity <= 0:
            raise ValueError("quantity must be positive")
        return self._prices.price_of(sku) * quantity
```

`QuoteService` is ordinary Python. A `Protocol` means the concrete price book
does not have to inherit from anything — anything with a compatible `price_of`
satisfies it. An abstract base class gives a louder error at construction time
but forces an import from the domain into every adapter. Pick one style and
apply it consistently; mixing both makes it unclear what a fake must implement.

## Middleware belongs on the edge

Logging, request identifiers, authentication, rate limiting and error mapping
are cross-cutting: they apply to every request, including the ones that never
reach the domain. Middleware is the right home because it runs once, in one
place, and a newly added route inherits it automatically.

The trap is pulling business rules into middleware. Middleware sees an opaque
request; it does not know that `POST /orders` and `DELETE /orders/{id}` need
different authorisation checks. *Authentication* answers "who is this?" and
produces a value the domain can consume. *Authorisation* for a specific
resource answers "may this actor do this to this object?", needs the object, and
belongs in the domain.

Ordering matters too. Middleware runs outside-in on the way in and inside-out on
the way out, so the outermost error mapper is the one that catches a domain
exception. If authentication sits inside that mapper, a rejected request can
escape as a stack trace instead of a `401`.

## Seams that make a service testable

A seam is a place where a test substitutes behaviour without a server. Cut four
on day one: the data store, the clock, the outbound client and the identifier
generator.

```python
def test_quote_multiplies_unit_price():
    service = QuoteService(FakePriceBook({"SKU-1": 250}))
    assert service.quote("SKU-1", 4) == 1000
```

No HTTP, no fixtures, no container. The routing layer still deserves an
integration test with a test client, but that test then only has to prove the
transport mapping: status codes, serialisation and validation errors. When the
layers are separate, each test is small enough to be honest about what it
covers.

Module-level side effects destroy seams. A connection pool created at import
time cannot be replaced per test and makes test order significant. Build
collaborators during start-up and store the assembled graph on the application
object.

## The failure mode: the request-shaped function

The anti-pattern is one `async def handler(request, response)` that validates,
queries, applies a discount, sends an email, mutates `response` and sets a
status code. Every symptom follows from that arrangement:

- the discount rule cannot be tested without a database, an HTTP object and a
  mail server;
- a retry re-sends the email, because the side effect sits inside the retried
  unit;
- moving to another transport — a queue consumer, a CLI — means copying logic;
- one function has four reasons to change, so every change risks all four.

The fix is not a large refactor. Extract the decision into a pure function that
takes values and returns a value, call it from the handler, and leave the
handler with transport work only. Once the rule has a name, it can be tested,
cited in review, and reused behind a different transport.

## Practice

Apply this in the [REST API Service challenge](../challenges/backend-engineering-rest-api-service):
keep the route thin, move decision logic into plain Python you can import
without starting a server, and confirm your tests still pass with the network
and database unavailable.
