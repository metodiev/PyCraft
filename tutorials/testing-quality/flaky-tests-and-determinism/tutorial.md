# Determinism: Why Tests Flake and How to Stop It

A test that fails every time is annoying and useful. A test that fails one run in
twenty is worse than useless: it teaches the team to press re-run, it hides the
real regression inside its noise, and it burns trust in the suite until nobody
reads a red build. Flakiness is not a property of the test runner — it is a
property of the test touching something that changes between runs.

## Where non-determinism enters

Almost every flake comes from one of a short list of inputs.

- Wall-clock time: `datetime.now()`, `time.time()`, `time.monotonic()`.
- Randomness: `random`, `secrets`, `uuid4`, hash randomisation.
- Iteration order: `set` and `dict` iteration, `os.listdir`, globbing files.
- Concurrency: threads and tasks interleaving, or an `async` function never awaited.
- Shared state: real network calls, the developer's filesystem, a reused database.
- Sleep-based synchronisation: `time.sleep(0.1)` racing a background thread.

Python randomises hash seeds for `str` and `bytes` on every process start
(`PYTHONHASHSEED`), so code that iterates a `set` of strings can produce different
orders in different runs. Nothing in the random branch changed — the test is
merely reading whatever order arrived. The same applies to file listings and to
dictionaries built from them.

A never-awaited coroutine is a special case worth naming: calling an `async def`
function produces a coroutine object and schedules nothing. Python 3.12 emits a
`RuntimeWarning` for it, but the surrounding test usually still passes, so a whole
assertion can silently disappear.

## Inject, don't call

The fix is to make the ambient input an explicit argument. Instead of asking the
system what time it is, hand the code a clock.

```python
from datetime import datetime, timezone

def is_expired(token, *, now=None):
    now = now or datetime.now(timezone.utc)
    return token.expires_at <= now
```

The production default keeps call sites unchanged, and the test states its own
truth:

```python
def test_expired_token_at_boundary():
    token = Token(expires_at=datetime(2030, 1, 1, tzinfo=timezone.utc))
    assert is_expired(token, now=datetime(2030, 1, 1, tzinfo=timezone.utc))
```

The same shape works for randomness (`rng: random.Random` or a callable), for ids
(`next_id: Callable[[], str]`), and for config. A parameter is honest — the
dependency is visible in the signature and in the test — whereas monkey-patching
`datetime` globally hides it and, because `datetime` is a C type, requires
awkward tricks that leak into unrelated modules.

When the dependency is genuinely global — a module-level cache, a process-wide
connection — prefer a fixture that seeds and restores it. Seed inside the fixture,
never inside the test body, so a failure cannot leave the global seeded for the
next test. And when a boundary is real, control it: point the client at a local
server or a recorded transport rather than the internet, and give each test its
own temp directory instead of writing to the working tree.

## Sleep is not synchronisation

`time.sleep(0.1)` encodes an assumption about machine speed. On a loaded CI
runner that assumption fails, and on a developer laptop it wastes time on every
green run. Wait on the condition instead — an event, a queue `join`, a thread
`join` with a timeout that raises when exceeded. Waiting with a generous timeout
makes a slow machine slower, not broken; sleeping makes it broken.

## Reproducing a flake on demand

Once a flake is suspected, make it deterministic rather than hoping to catch it.
Record the seed, then replay it. pytest's own collection order is deterministic,
but the hash seed is set per process and anything your code derives from the
filesystem or from a random source is not, so pin those inputs explicitly:

```bash
PYTHONHASHSEED=0 pytest -p no:randomly --tb=short tests/test_pipeline.py -x
```

Run the file alone, then run the whole suite, because most flakes are order- or
state-dependent and only appear in one of the two. A failing seed you can re-run
converts "sometimes red" into a normal bug with a stack trace. If the failure
disappears when the file runs alone, suspect leaked state: a module-level mutable
default, an unclosed resource, or a fixture that does not reset what it mutates.

Finally, treat a flake as a defect with the same weight as a production bug.
Quarantine it, mark it, and fix it — but never let it sit in the suite silently
failing. The [Flaky Test Detector](../challenges/testing-quality-flaky-test-detector)
challenge asks you to build exactly that verdict from recorded run histories: a
test that fails in some runs and passes in others is quarantined, and the
decision must be reproducible from the recorded data rather than from a guess.

## Practice

Implement [Flaky Test Detector](../challenges/testing-quality-flaky-test-detector),
then revisit [pytest Fundamentals](../tutorials/testing-quality-pytest-fundamentals) to see how scope choices
create order-dependent state. The [challenges](../challenges) catalogue lists what
comes next.

<details><summary>Hint: finding the seeded runs</summary>

Log the random seed and the environment variables that affect ordering at the
start of a failing run. A flake you cannot replay is a flake you cannot fix.

</details>
