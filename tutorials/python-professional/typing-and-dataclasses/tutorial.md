# Type Hints and Dataclasses That Earn Their Keep

Type hints are documentation that tooling can check, and dataclasses are a
`__init__` generator with opinions. Used together they remove a whole class of
"it was `None` last Thursday" bugs — but only if you know which parts run and which
parts are merely promises, because the two halves of this topic fail in opposite ways.

## Annotations are not enforced

An annotation is stored; it is not checked. Nothing at runtime compares the value to the
hint, so the following runs happily and returns `None`:

```python
def total(prices: list[int]) -> int:
    return sum(prices)

total(["1", "2"])   # TypeError: unsupported operand type(s) for +: 'int' and 'str'
```

The failure surfaces inside the function, at the point where the wrong type happens to
break, not at the call site where the mistake was made. Annotations buy you static
analysis and editor completion, not guarantees. The library you want when you *do* need
runtime checking is Pydantic, and the discipline of validating at the boundary rather
than sprinkling `isinstance` checks through the core.

You can read them back, which is how frameworks build serialisers and dependency
injection:

```python
def f(x: int) -> str: ...
f.__annotations__            # {'x': <class 'int'>, 'return': <class 'str'>}
```

## from __future__ import annotations

Add this import at the top of every module you write:

```python
from __future__ import annotations

def lookup(rows: list[dict[str, int]]) -> dict[str, int] | None: ...
```

It makes all annotations lazy: they are stored as strings and never evaluated at
definition time. Three things follow. Forward references work without quotes, so a class
may mention itself. Import cost drops, since annotations no longer execute. And the
`list[str]` syntax becomes legal on versions older than 3.9, because the expression is
never evaluated. The trade-off is that anything reading `__annotations__` directly now
gets strings — use `typing.get_type_hints()` when you need evaluated objects, which also
resolves those forward references.

Note that PEP 649 in Python 3.14 changes the mechanism to lazy evaluation by default, so
this import becomes unnecessary there, but it remains correct and harmless.

## list[str] versus List[str]

Since Python 3.9, builtin generics are subscriptable: `list[str]`, `dict[str, int]`,
`tuple[int, ...]`. The `typing.List` spellings are aliases kept for older versions. In
new code on 3.12 there is no reason to import them, and `from __future__ import
annotations` makes the modern form safe even in code that must also run on 3.8.

```python
from typing import Optional

def find(rows: list[str], needle: str) -> Optional[str]: ...      # pre-3.10
def find(rows: list[str], needle: str) -> str | None: ...          # 3.10+
```

`X | None` is the modern union. `Optional[X]` does not mean "may be omitted" — it means
exactly `X | None`, and a parameter with no default is still required even if it is
annotated `Optional`. That mismatch between the English word and the type is one of the
most common misreadings in Python code.

Two more vocabulary notes. `Any` disables checking for that value and propagates: a value
of type `Any` silences every error downstream, so it tends to spread. Use `object` when
you mean "anything at all, and I will narrow it", and reserve `Any` for genuinely
dynamic boundaries. `Iterable[str]` describes a parameter you will only loop over;
`Sequence[str]` adds indexing and length; `list[str]` promises a mutable list, which
tells the caller you might modify their data.

## Dataclass essentials

`@dataclass` reads the class annotations and writes `__init__`, `__repr__` and `__eq__`
for you:

```python
from dataclasses import dataclass, field

@dataclass(frozen=True, slots=True)
class Order:
    id: int
    items: list[str] = field(default_factory=list)
    note: str = ""
```

`frozen=True` makes instances immutable: assignment raises `FrozenInstanceError`, and
hash is generated, so instances can be dict keys or set members. That matters whenever
you intend to use the object as a key, and it kills accidental shared-state bugs.

`slots=True` generates `__slots__`, dropping the per-instance `__dict__`. Instances get
smaller and attribute access is marginally faster, at the cost of not being able to add
attributes dynamically. It is only worth reaching for on objects you create in large
numbers, and it constrains multiple inheritance: combining two slotted base classes that
each declare their own slots fails with `TypeError: multiple bases have instance lay-out
conflict`.

The mutable-default trap is the one that bites hardest. A bare list default would be
shared by every instance, so the dataclass decorator rejects it outright:

```python
@dataclass
class Bad:
    items: list[str] = []      # ValueError: mutable default ... use default_factory
```

`default_factory` takes a callable and invokes it per instance, which is precisely the
fix. The same applies to `dict`, `set` and any custom mutable object. A `Field` with
`default_factory` is also how you express "computed at construction time".

Use `__post_init__` for validation and derived fields, remembering that frozen instances
need `object.__setattr__` to set anything after the generated `__init__` has run:

```python
@dataclass(frozen=True)
class Range:
    low: int
    high: int

    def __post_init__(self):
        if self.high < self.low:
            raise ValueError(f"high {self.high} < low {self.low}")
```

`field(compare=False)` excludes a field from `__eq__`, and `field(repr=False)` hides one
from the repr — useful for large payloads and for secrets you do not want in a log line.

## When a dataclass beats a dict or a plain class

Prefer a dataclass when the keys are known in advance, you want `==` and a readable
`repr`, and the values have different types. Prefer a `dict` when the keys are data
themselves — counts by hostname, JSON you are passing through, a cache. Prefer a plain
class when you need non-trivial behaviour, inheritance with custom initialisation, or a
public API that should not expose its fields as constructor arguments.

The cost of a dict for structured records is that every access goes through a string
key that no tool can check: a typo is a `KeyError` at runtime rather than an error
underlined in your editor. The cost of a dataclass is boilerplate when you only ever
want to hand the mapping to `json.dumps`. If the code round-trips between the two,
`dataclasses.asdict()` and `MyClass(**payload)` convert both ways, but the reverse
direction checks names only — it rejects a missing or unexpected key and silently accepts
`Order(id="not-an-int")`, because the annotation is not enforced. Real serialisers validate
before constructing.

## Practice

[DATACLASS SERIALIZER](../challenges/python-professional-dataclass-serializer) asks you
to round-trip nested dataclasses through plain dicts with real type validation — the
point where `asdict` stops being enough.

<details><summary>Hint: walking fields, not payload keys</summary>

Walk the dataclass fields rather than the payload keys, and use `typing.get_type_hints`
to resolve nested types. Validate before constructing; do not rely on `__post_init__` to
catch missing keys.

</details>
