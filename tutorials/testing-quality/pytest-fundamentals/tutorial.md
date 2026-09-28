# pytest Fundamentals: Assertions, Fixtures and Parametrisation

pytest is small enough to learn in an afternoon and deep enough that most teams
use a fraction of it. The parts that repay attention are the ones that decide
how quickly a failure explains itself: what assertion rewriting prints, what a
fixture really is, and how a parametrised table replaces a dozen near-identical
functions.

## Bare `assert` is enough

A test does not need a special assertion API, because pytest rewrites the module
before it is imported. It parses each test file, finds `assert` statements, and
recompiles them so a failure reports the sub-expressions that produced it.

```python
def test_total_is_sum_of_parts():
    parts = [1, 2, 3]
    assert sum(parts) == 6, "running total drifted"
```

When that fails, the traceback shows the values of `sum(parts)` and `6`
side by side. Two consequences follow. First, plain `assert` still works outside
pytest, so production code can use it for invariants. Second, rewriting only
applies to test modules that pytest imports itself — an assert buried inside an
imported helper library fails without the nice display. Check it with
`pytest --assert=plain` if you ever need to remove all doubt.

Avoid `assert x == True`, `assert len(items)`, and truthiness checks on optional
values: `assert items` passes for an empty list and tells you nothing about what
was expected. Compare values directly.

## Discovery rules

pytest collects only what matches its default patterns:

| Pattern | Default |
| ----- | ----- |
| Files | `test_*.py` or `*_test.py` |
| Functions | `test_*` at module level |
| Classes | `Test*`, with no `__init__` |
| Methods | `test_*` inside those classes |

Two traps live here. A class named `TestHelper` with an `__init__` is silently
skipped unless you also pass `__init__`-collecting options; use plain functions
unless you need shared state. And a test that never runs looks exactly like a
test that passes in CI output — `pytest --collect-only -q` shows what was
actually gathered, which is the first thing to check when a new file "passes"
instantly.

## Fixtures: dependency injection and scope

A fixture is a function whose return value is injected into any test that names
it as a parameter. Setup and teardown live in the same function, separated by
`yield`.

```python
import pytest

@pytest.fixture
def account():
    acct = {"balance": 100, "frozen": False}
    yield acct
    acct.clear()
```

A test asks for it by parameter name:

```python
def test_withdraw_reduces_balance(account):
    account["balance"] -= 30
    assert account["balance"] == 70
```

pytest resolves the name from the fixture registry, runs the setup, passes the
object, and runs code after `yield` once the test finishes. Requests are cached
within a scope, so asking for `account` twice inside one test returns the same
object rather than building it twice. Widen the scope and that caching widens
with it: a session-scoped fixture is built once for the whole run and handed to
every test that asks for it.

Function scope (the default) gives every test a clean object. Module, class,
session and package scopes trade that isolation for speed. The trade is only
worth making when construction is genuinely expensive — a database container,
a populated schema — and the object is not mutated by tests. A session-scoped
fixture that one test mutates will produce failures that depend on test order,
which is the worst class of bug to debug because reordering your selection makes
it disappear. If you must share something expensive, share it read-only, or add
an autouse function-scoped fixture that resets the mutable part around each test.

## Parametrisation builds a table

Instead of copying a test per case, describe the cases as data:

```python
@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("3+4", 7),
        ("-1", -1),
        ("12", 12),
    ],
)
def test_evaluate(text, expected):
    assert evaluate(text) == expected
```

Each tuple becomes a separate test with an id derived from the arguments, so one
bad row fails alone and the others still report. Use `pytest.param(..., id="...")`
when auto-generated ids are unreadable, and stacking two `parametrize` decorators
produces the cartesian product of both sets — useful for input/format matrices,
surprising when you expected zipping.

## Checking exceptions precisely

`pytest.raises` fails if nothing is raised, and captures the exception for
inspection:

```python
def test_divide_by_zero_message():
    with pytest.raises(ZeroDivisionError, match="division by zero"):
        divide(1, 0)
```

`match` takes a regular expression tested against `str(exc)` with `re.search`, so
`match="value"` matches any message containing it. Two mistakes are common: using
a regex metacharacter unintentionally (`match="420 (kg)"` will not match that
literal text), and asserting only the type when the test exists to pin the
message. Also check that the right call raised — an exception from a line you did
not intend still satisfies the context manager, so keep the `with` block narrow.

## Practice

Apply this in the [Property Checking Loop](../challenges/testing-quality-property-checking-loop)
challenge, then read [Test Doubles: Spies, Stubs and Mocks](../tutorials/testing-quality-test-doubles) for the
next step. Browse the full [tutorials](../tutorials) index or the
[challenges](../challenges) catalogue.

<details><summary>Hint: collecting without running</summary>

`pytest --collect-only -q` lists every test id pytest found. If a file you
expect to appear is missing, the discovery rules above are the reason.

</details>
