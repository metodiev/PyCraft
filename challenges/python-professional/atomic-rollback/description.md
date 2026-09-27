# Atomic Rollback

Configuration reloads, cache warm-ups, in-memory registries: any code that
mutates shared state half-way and then blows up leaves the process in a state
nobody designed. Wrap the risky section in a context manager that rolls the
mapping back to exactly what it was.

## Your task

Complete the function `atomic(store)` so it returns a **context manager** that
makes mutations of the mapping `store` all-or-nothing.

### Behaviour

| Requirement | Detail |
| ----------- | ------ |
| Live view | Inside the block, mutations are visible immediately. `store` is never replaced or copied for the caller — the very same object keeps the mutations while the block runs. |
| Success | If the block finishes normally, the mutations are kept and the context manager returns falsy (an exception was not handled). |
| Failure | If the block raises, `store` is restored to its exact contents at `with` entry, and the **same exception object** continues to propagate. |
| Exact restore | Keys added inside the block are gone; keys deleted inside the block are back; keys whose value changed are back to the old value. Restoring may reorder the mapping's iteration order — only equality of content is checked. |
| Any exception | `BaseException` subclasses such as `KeyboardInterrupt` or `SystemExit` roll back too — do not catch `Exception` only. |
| Nesting | Nested blocks each restore to their own entry state. When the inner block succeeds but the outer one fails, the whole outer block is rolled back. |
| Reuse | Calling `atomic(store)` again — before or after other blocks — starts a fresh snapshot. |

`store` is any mutable mapping with `__setitem__`, `__delitem__` and
`__iter__` — a plain `dict` in the tests.

## Examples

```python
config = {"debug": False}

with atomic(config):
    config["debug"] = True
    config["level"] = 3
# config == {"debug": True, "level": 3}

config = {"debug": False, "level": 3}
try:
    with atomic(config):
        config["debug"] = True
        del config["level"]
        config["extra"] = "added"
        raise RuntimeError("bad config")
except RuntimeError:
    pass
# config == {"debug": False, "level": 3}
```

## Constraints

* Standard library only (`contextlib` is allowed and idiomatic).
* Do not swallow exceptions: `__exit__` must return `False`/`None`.
* The rolled-back mapping must contain exactly the same key/value pairs as
  before, and must be the same object the caller passed in.

## Hints

<details>
<summary>Hint 1 — Snapshot both directions</summary>

Saving a copy of the old contents is only half the story: you also need to
remove keys that appeared afterwards. A snapshot that records both the old
values and the old key set lets you restore either way:

```python
snapshot = dict(store)
...
store.clear()
store.update(snapshot)
```

</details>

<details>
<summary>Hint 2 — contextlib.contextmanager</summary>

A generator-based context manager keeps this short. The `try/except
BaseException` must re-raise; only the cleanup belongs in the failure branch:

```python
import contextlib

@contextlib.contextmanager
def atomic(store):
    snapshot = dict(store)
    try:
        yield store
    except BaseException:
        store.clear()
        store.update(snapshot)
        raise
```

A class with `__enter__`/`__exit__` works just as well — `__exit__` returns
`False` so the exception keeps propagating.

</details>
