# Property Checking Loop

Example-based tests check a handful of inputs you already thought of.
Property-based testing checks hundreds you did not — and when one fails, it
hands you a *minimal* counterexample instead of a random mess. Build the engine
behind that, with no third-party library.

## Your task

Implement `check(prop, generate, trials=100, seed=0)` and the `Report` type.

```python
report = check(lambda text: len(text) >= 0, lambda rng: "x" * rng.randint(0, 5))
```

### `Report`

An immutable value object with these attributes:

| Attribute | Meaning |
| --------- | ------- |
| `passed` | `True` only if every trial passed |
| `trials_run` | How many trials actually ran |
| `counterexample` | The failing input, or `None` when `passed` |
| `error` | `None` when the property returned `False`; the exception's **message** (a `str`) when it raised |
| `seed` | The seed that was used (default `0`) |

`Report` supports equality with another `Report` and is truthy exactly when
`passed` is `True` (`bool(report) is True` on success).

### `check(prop, generate, trials=100, seed=0)`

1. Build `rng = random.Random(seed)` — **one** generator for the whole run.
2. For up to `trials` iterations: call `candidate = generate(rng)`, then
   `prop(candidate)`.
3. If `prop` returns a falsy value, or raises any `Exception`, stop and report a
   failure with that input as the `counterexample`.
4. If nothing fails, report a pass with `trials_run == trials`.

Details that matter:

* **Deterministic**: the same `seed` produces the same sequence of candidates
  and therefore the same `Report`.
* **Shrinking**: when a failing counterexample is an `int` (but not a `bool`),
  reduce it to the failing value closest to zero, so the learner sees the
  tightest failing case rather than a random one. Shrinking **never changes the
  sign**. Define `fails(x)` as "`prop(x)` is falsy or raises". Then:
  * `value == 0` → stays `0`.
  * `value > 0` → if `fails(0)`, the counterexample is `0`. Otherwise
    **binary-search** the interval between `0` and `value` and return the
    smallest integer that still fails.
  * `value < 0` → the mirror image: if `fails(0)`, the counterexample is `0`;
    otherwise return the largest (closest to zero) integer that still fails.

  This is a bounded search (it never needs more than `log2(|value|)` extra
  property calls), so a property that is slow cannot spin forever. For a
  monotone property such as `n <= 10` a random failing candidate of `500`
  shrinks to exactly `11`.
* **Both directions**: a property that raises counts as failing while shrinking
  too — but a shrunk candidate that raises keeps its `error` text, so `Report`
  must carry the error of the value it actually returns.
* **Exceptions are failures**: the `error` is `str(exception)` — do not let them
  escape.
* `trials < 0` raises `ValueError`. `trials == 0` is a pass with
  `trials_run == 0`.
* A generator that runs out (e.g. `generate` raises `StopIteration`'s parent
  `Exception`) is a failure, not a crash.

## Examples

```python
always_ok = check(lambda n: n == n, lambda rng: rng.randint(0, 10), trials=5)
always_ok.passed          # True
always_ok.counterexample  # None
always_ok.error           # None

# fails for every candidate > 10, so shrinking lands exactly on 11
report = check(lambda n: n <= 10, lambda rng: rng.randint(0, 1000), trials=200, seed=1)
report.passed             # False
report.counterexample     # 11

def blows_up(n):
    raise ZeroDivisionError("division by zero")

boom = check(blows_up, lambda rng: rng.randint(1, 5))
boom.passed               # False
boom.error                # "division by zero"
```

## Constraints

* Standard library only — `random` and `dataclasses` are expected.
* No printing; return the `Report`.
* `check` must not mutate `generate` or `prop`; treat them as callables.
* `Report` must be usable as a value: build two reports from identical arguments
  and they must compare equal.

## Hints

<details>
<summary>Hint 1 — Report as a frozen dataclass</summary>

```python
import dataclasses

@dataclasses.dataclass(frozen=True)
class Report:
    passed: bool
    trials_run: int
    counterexample: object = None
    error: str | None = None
    seed: int = 0
```

A frozen dataclass gets you equality for free. Add `__bool__` returning
`self.passed` so `if report:` reads naturally.

</details>

<details>
<summary>Hint 2 — Shrinking an integer counterexample</summary>

Shrinking is just "try something smaller, keep it if it still fails":

```python
def _smaller(value):
    if value > 0:
        return value // 2
    if value < 0:
        return -((-value) // 2)
    return value

candidate = failing_value
while True:
    trial = _smaller(candidate)
    if trial == candidate or _fails(trial) is not True:
        break
    candidate = trial
```

Re-run the property with a bounded number of attempts (say 64) so a property
that hangs cannot spin forever, and remember that a *raising* property counts as
failing for the purposes of shrinking.
</details>
