# Spy and Stub

Every mocking library is built from two tiny pieces: a **spy** that records what
it was called with, and a **stub** that returns scripted values instead of doing
real work. Build both, from scratch, with no third-party library involved.

## Your task

Implement a `Spy` class and a `Call` value type. Standard library only.

### `Call`

A small immutable record of a single invocation exposing two attributes:

| Attribute | Meaning |
| --------- | ------- |
| `args` | tuple of positional arguments (may be empty) |
| `kwargs` | dict of keyword arguments, always a **fresh copy** |

`Call` must support equality with another `Call` and expose both attributes.

### `Spy`

```python
spy = Spy()                       # returns None
spy = Spy(target=real_function)   # delegates to real_function
```

| Member | Behaviour |
| ------ | --------- |
| `spy(*args, **kwargs)` | Records the call as `Call(args, kwargs)` and returns the configured result (see below). |
| `spy.calls` | List of `Call` objects in call order. Must return a **new list** each time, and each returned `Call` must carry its own copy of the keyword dict — nothing a caller does to the returned objects may alter the history. |
| `spy.call_count` | Number of recorded calls. |
| `spy.return_value` | Value returned by default. Initially `None`. |
| `spy.side_effect` | A **list** consumed one item per call. An item that is an exception instance **or an exception class** is raised; anything else is returned. When the list runs out, normal behaviour resumes. |
| `spy.target` | The wrapped callable (or `None`). When set, it is called with the same arguments and its return value is passed through — unless `return_value` or a `side_effect` item takes precedence. |
| `spy.assert_called_once()` | Raises `AssertionError` if `call_count != 1`. |
| `spy.assert_called_with(*args, **kwargs)` | Raises `AssertionError` if there are no calls or the **last** call does not match exactly (positional *and* keyword arguments, order-insensitive for keywords). |
| `spy.assert_not_called()` | Raises `AssertionError` if there was any call. |
| `spy.reset()` | Clears `calls` but keeps the configuration (`target`, `return_value`, `side_effect`). |

### Result precedence

Per call, in order:

1. `side_effect` has a pending item → raise it if it is an exception class or
   instance, otherwise return it.
2. `target` is set → return `target(*args, **kwargs)`.
3. Otherwise → return `return_value`.

## Examples

```python
spy = Spy()
spy(1, key="a")
spy.calls == [Call((1,), {"key": "a"})]
spy.call_count == 2 - 1          # 0 after reset(), 1 here

stub = Spy()
stub.return_value = 7
stub()                           # -> 7

scripted = Spy()
scripted.side_effect = [KeyError("missing"), "then fine"]
scripted()                       # -> raises KeyError (the class form works too)
scripted()                       # -> "then fine"
```

## Constraints

* Standard library only (`collections.namedtuple`/`dataclasses` are fine).
* `Spy` instances must be callable, and the tests treat them as plain test
  doubles — no metaclasses or monkeypatching needed.
* Never let a caller mutate your recorded history: `spy.calls.append("junk")`
  must leave `spy.call_count` unchanged.
* `assert_*` failures must be `AssertionError`, not a custom exception.

## Hints

<details>
<summary>Hint 1 — Recording faithfully</summary>

Keep the internal list private and hand out copies:

```python
class Spy:
    def __init__(self, target=None):
        self.target = target
        self.return_value = None
        self.side_effect = []
        self._calls = []

    @property
    def calls(self):
        return list(self._calls)
```

`Call` can be a `collections.namedtuple("Call", "args kwargs")`, which already
gives equality, but remember the `kwargs` dict inside it is shared — build a
fresh dict when you record.

</details>

<details>
<summary>Hint 2 — Exceptions as values</summary>

`issubclass(item, BaseException)` tells you the item is an exception *class*;
`isinstance(item, BaseException)` tells you it is an *instance*. Both must be
raised, and instances should be raised unchanged so the test can assert on
identity:

```python
if isinstance(item, BaseException) or (
    isinstance(item, type) and issubclass(item, BaseException)
):
    raise item
return item
```
</details>
