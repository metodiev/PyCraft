# SOLID and the Boundaries That Matter

SOLID is taught as five slogans, which is why it produces code with an interface for everything and a class for each interface. Each principle is a specific answer to a specific pain: a change that ripples further than it should. Read them as five diagnoses, not five rules.

## Single responsibility: one axis of change

"One reason to change" does not mean one method. It means one *axis* of change — one group of stakeholders or one forcing function that makes you edit the file.

A `Report` class that formats a document, writes it to S3, and emails it has three axes: formatting rules change when the design team changes them, the storage path changes when infrastructure changes, and the notification changes when product changes. A class with forty methods that all change for the same reason has one responsibility and is perfectly cohesive. Two methods, one of which changes when the tax rules change and the other when the currency table does, is two responsibilities wearing one class.

The test is not size. It is: when this changes, what else in the file has to change with it?

## Open/closed: earn your extension points

The open/closed principle says a module should be open to extension and closed to modification — you add behaviour without editing what exists. The practical version is not "add a hook everywhere"; it is "put the seam where the variation actually happened".

An invoice calculator with a `discount_policy` parameter that is called once with a fixed implementation is not extensible, it is speculative. The counter-example is a system that has had four discount rules in six months: the fourth is the evidence that a policy interface is warranted, and the first three should have been written as plain code. Adding an extension point costs a layer of indirection forever, and it is paid for by every reader of the code, including the one trying to find out what actually runs in production.

If you want the diagnostic: an abstraction used by exactly one implementation, with no test double and no second caller on the roadmap, is ceremony.

## Liskov substitution: the fragile base class

LSP says an object of a subtype must be usable anywhere the supertype is, without the caller knowing. The failure mode is the class that inherits a behaviour and then has to break it: a `Square` that inherits `Rectangle` and must make `set_width` also set height, or a read-only collection that inherits a mutable one and throws on `append`.

The real cost is not the throw; it is that every caller now has to know which subtype it holds. Once a method can fail depending on the concrete class, the abstraction has stopped abstracting and becomes a lookup table of special cases. Two defences work: prefer composition to inheritance when the relationship is "has a" or "behaves like but not always", and when overriding, keep the preconditions no stronger and the postconditions no weaker than the parent's. If the subclass needs to weaken the contract, it is not a subtype — it is a sibling.

## Interface segregation and dependency inversion

Interface segregation is the first consumer of dependency inversion, so they are best taken together. ISP says no client should be forced to depend on methods it does not use. A fat `UserService` with twelve methods forces a component that only needs `get_user` to be coupled to the other eleven and, in most languages, to their transitive imports too. Splitting per client need shrinks the blast radius of every change.

DIP does the most work of the five. The rule is that high-level policy should not depend on low-level detail; both should depend on an abstraction. The subtle part is *who owns* the abstraction.

```python
from typing import Protocol

class OrderRepository(Protocol):
    def get(self, order_id: str) -> Order: ...
    def save(self, order: Order) -> None: ...

def place_order(repo: OrderRepository, order: Order) -> None:
    repo.save(order)
```

`OrderRepository` is defined in terms of `Order` — a domain concept — and lives next to the order logic that uses it. The PostgreSQL implementation imports this protocol, not the other way around. That inversion is what lets you change the storage engine without touching the domain, and it is what makes the domain testable against an in-memory fake.

```python
class FakeOrders:
    def __init__(self) -> None:
        self.saved: list[Order] = []
    def get(self, order_id: str) -> Order: ...
    def save(self, order: Order) -> None:
        self.saved.append(order)

def test_place_order_records_the_order() -> None:
    repo = FakeOrders()
    place_order(repo, Order(id="A1", total=250))
    assert [o.id for o in repo.saved] == ["A1"]
```

## The price of a wrong boundary

Every boundary you draw costs a translation layer, an extra file, and a name that both sides must agree on. Boundaries pay for themselves when the thing behind them changes — a database that will be swapped, a vendor that will be replaced, a rule that will be varied. They are pure cost when the detail is stable: an abstraction over `datetime.now()` that is never faked costs more than the direct call ever would.

So draw boundaries where change is expected or where testing demands it, and write down which of the two reasons applies. A boundary with no stated reason is the one that will be maintained for a decade and understood by no one.

## Practice

[Multi-tenant SaaS Backend](../challenges/software-architecture-multi-tenant-saas) requires a storage boundary that makes it impossible to ask for another tenant's rows. That is DIP earning its keep: the domain defines what it needs, and the adapter is where isolation is enforced.
