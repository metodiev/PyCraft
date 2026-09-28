# Memory Behaviour: Objects, References and Leaks

Every name in Python is a reference to an object on the heap. Memory problems
almost never come from a single large object; they come from references that
were kept alive longer than the author believed, and from measurements taken at
the wrong level.

## Names, objects and identity

`x = [1, 2]` binds the name `x` to a heap object. Calling a function passes
that reference, not a copy, so a function that mutates its argument mutates the
caller's object. Rebinding a name inside a function, by contrast, only changes
the local name.

`==` compares values by calling `__eq__`; `is` compares identity by object
address. Two equal lists are never `is`-identical. Identity is the right
question for sentinels (`x is None`) and for interning-sensitive checks; values
are the right question for everything else.

## Reference counting, with a cycle collector as backup

CPython frees an object when its reference count drops to zero, which makes most
cleanup prompt and predictable. Reference counting cannot free cycles — a node
that points at itself, or two objects pointing at each other, keeps counts above
zero forever. The cyclic garbage collector exists for exactly that case: it
periodically walks container objects, finds unreachable cycles and frees them.

Consequences you can observe:

- `del name` drops one reference; the object dies only if that was the last one.
- A cycle is freed at collection time, not at the moment it becomes garbage, so
  `__del__` in a cyclic structure runs late — or not at all if the interpreter
  exits during shutdown.
- Objects with `__del__` in a cycle involving other finalised objects can be
  uncollectable, which is why relying on finalisers for resource release is
  fragile. Use context managers.

## sizeof lies about containers

`sys.getsizeof` reports the size of the object itself and not of the objects it
points at. A list of 1000 integers reports roughly its own array of pointers —
about 8 KB — and nothing at all for the integers those pointers reference, each
of which is a separate heap object of about 28 bytes (only small integers in
−5..256 are cached and shared).

```python
import sys

items = list(range(1000))
print(sys.getsizeof(items))          # the list object only
print(sys.getsizeof(items[0]))       # one int object: the container does not own it

import tracemalloc

tracemalloc.start()
before = tracemalloc.take_snapshot()
data = [dict(key=i) for i in range(10_000)]
after = tracemalloc.take_snapshot()
for stat in after.compare_to(before, "lineno")[:3]:
    print(stat)
```

`tracemalloc` answers a different question — "what did this code allocate?" — by
recording the traceback of each allocation. Snapshot comparison gives you size,
count and the line that produced it, which is what you actually need for growth.

## Three common accidental leaks

**A module-level cache that only grows.** A dictionary memo keyed by input is a
leak with good intentions: nothing evicts entries, so peak memory tracks the
union of everything ever processed. Use `functools.lru_cache` with a bounded
`maxsize`, or an explicit bounded structure. An unbounded cache behind a
long-lived process is a scheduled outage.

**A closure holding a large object alive.** A callback that references one
attribute of a large object still keeps the whole object reachable, unless it
captures the attribute instead:

```python
class Report:
    def __init__(self, rows, blob):
        self.rows, self.blob = rows, blob

    def make_callback(self):
        return lambda: self.rows[0]     # keeps the Report, and ``blob``, alive
```

The fix is to bind what is needed: `rows = self.rows` and close over `rows`.

**An exception traceback keeping frames alive.** `sys.exc_info()` and any stored
exception hold a traceback, and a traceback holds every frame in the stack with
its locals — including that 50 MB buffer. An exception logged and discarded is
fine; an exception stored in a list, or bound to `e` in a long-lived scope,
pins everything the stack referenced. `raise ... from None` hides the chained
traceback from the output but keeps `__context__` on the exception, so it does
not free the cause: it is a readability tool, not a memory one. To release the
frames, delete the reference — `except Exception as exc: ...; del exc`, or
avoid storing the exception object at all — and never accumulate exceptions as a
diagnostic log.

## Bounded peak memory

Streaming is the general cure. A generator yields one item at a time, so peak
memory is the size of the item, not the size of the collection:

```python
def streaming_rows(path):
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            yield line.rstrip("\n").split(",")
```

Generators buy bounded memory at the price of single-pass iteration and lazy
side effects. When you need the result twice, materialise deliberately and
measure, rather than trusting "it is only a list".

## Practice

Use [Range Sum Queries](../challenges/performance-range-sum-queries) to observe
the trade in the other direction: your prefix array costs memory on purpose.
Measure both with `tracemalloc`, and check that your stated space budget matches
what the interpreter actually allocates.
