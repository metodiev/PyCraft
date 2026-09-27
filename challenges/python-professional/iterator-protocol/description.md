# Iterator Protocol

`for` loops, `list()`, unpacking and `in` all work through the same two dunder
methods — and the difference between *iterable* and *iterator* is exactly where
beginners get burned. Build both, with behaviour strict enough that a shallow
implementation fails.

## Your task

Implement `StepRange` (an **iterable**) and `Countdown` (an **iterator**).

### `StepRange(start, stop, step=1)`

A restartable, re-iterable range-like object.

| Requirement | Detail |
| ----------- | ------ |
| Iterable | `iter(obj)` returns a **new** iterator every time, so the object can be iterated repeatedly and by nested loops. |
| Half-open | Values are `start, start + step, ...` while `< stop` (when `step > 0`) or `> stop` (when `step < 0`). |
| `len()` | `len(obj)` returns the number of items it will produce. |
| `in` | `x in obj` works and must use the iterator protocol (no `range` object inside). |
| Equality | Two `StepRange` objects compare equal when they produce the same sequence — `StepRange(0, 5, 1) == StepRange(0, 5)` is `True`. |
| Representation | `repr(obj)` is exactly `StepRange(start, stop, step)`, e.g. `StepRange(0, 4, 2)`. |
| Validation | `step == 0` raises `ValueError`. Any of the three may be negative; `start`/`stop`/`step` must be `int`s (booleans rejected) or `ValueError` is raised. |
| Immutability | Setting any attribute raises `AttributeError`. |

`StepRange` itself must **not** be an iterator: calling `iter()` on it twice must
give two independent objects, and `StepRange(0, 3)` must stay unconsumed after
`list(...)`.

### `Countdown(start)`

A single-use iterator that yields `start, start - 1, ..., 1`.

| Requirement | Detail |
| ----------- | ------ |
| `next()` | Returns the next value; raises `StopIteration` **with no message** when finished. |
| Exhausted forever | Once exhausted it stays exhausted: further `next()` calls raise `StopIteration` again (they must not restart or raise anything else). |
| Self-iterating | `iter(obj) is obj` is `True`. |
| `__next__` | Calling `obj.__next__()` directly works exactly like `next(obj)`. |
| For | `list(Countdown(3))` is `[3, 2, 1]` and a second `list(...)` of the *same object* is `[]`. |
| Validation | `start` must be an `int >= 0` (booleans rejected), else `ValueError`. `Countdown(0)` is immediately exhausted. |

## Examples

| Call | Expected result |
| ---- | --------------- |
| `list(StepRange(0, 5, 2))` | `[0, 2, 4]` |
| `list(StepRange(5, 0, -2))` | `[5, 3, 1]` |
| `list(StepRange(3, 0))` | `[]` |
| `len(StepRange(0, 10, 3))` | `4` |
| `repr(StepRange(1, 2, 3))` | `"StepRange(1, 2, 3)"` |
| `list(Countdown(3))` | `[3, 2, 1]` |
| `list(Countdown(0))` | `[]` |
| `StepRange(0, 1, 0)` | raises `ValueError` |

## Constraints

* Standard library only.
* Do not subclass `range` or wrap a `range` instance — implement the arithmetic
  yourself. (`isinstance(obj, range)` must be `False` inside your class.)
* `len()` must be exact for negative steps too.

## Hints

<details>
<summary>Hint 1 — Iterable vs iterator</summary>

An *iterable* implements `__iter__` and returns a fresh iterator; an *iterator*
implements both `__iter__` (returning `self`) and `__next__`. That is the whole
difference, and it is what makes `StepRange` reusable and `Countdown` one-shot.

```python
class StepRange:
    def __iter__(self):
        current = self.start
        while (current < self.stop) if self.step > 0 else (current > self.stop):
            yield current
            current += self.step
```

A generator method is the shortest correct `__iter__`: each call creates a new
generator object, which is itself the fresh iterator.

</details>

<details>
<summary>Hint 2 — Length and exhaustion bookkeeping</summary>

The number of items in a half-open stepped range is:

```python
def _length(start, stop, step):
    if step > 0:
        return max(0, (stop - start + step - 1) // step)
    return max(0, (start - stop - step - 1) // (-step))
```

For `Countdown`, keep a `_remaining` counter and check it **before** yielding;
raise `StopIteration` (bare, no arguments) once it hits zero. Do not "reset" the
counter afterwards — an exhausted iterator must stay exhausted.
</details>
