# Project: Asynchronous Job Processing System

**This is a project, not a drill.** Three modules must cooperate — a retry
policy, a bounded worker pool and the system that wires them together — and the
tests drive them directly, with no broker, no network and no real waiting.

The interesting part is not "run some coroutines". It is that **asynchronous
code fails in ways that look like success**: a job quietly disappears when the
worker holding it raises, a semaphore released one line too early means the cap
was never enforced, a queue that "shuts down" instantly has simply abandoned the
work it accepted, and a retry loop that forgot its budget retries forever.

| File | Responsibility |
| ---- | -------------- |
| `retry.py` | Policy only: retryability decisions and the delay curve. Never sleeps |
| `jobqueue.py` | Scheduling: the concurrency cap, the retry loop, the dead-letter queue |
| `system.py` | Accounting: submission, running, per-job results, errors and statistics |

## Your task

### `retry.py` — `RetryPolicy`

`RetryPolicy` is passive: it never sleeps and never touches the event loop. It
answers two questions and leaves the clock to its caller, which is what makes
retry behaviour testable without waiting for anything.

| Name | Contract |
| ---- | -------- |
| `RetryPolicy(max_attempts=3, *, base_delay=0.1, multiplier=2.0, max_delay=None, jitter=0.0, retry_on=None, rng=None)` | Validate and store the configuration |
| `is_retryable(exc)` | May this exception be retried at all? |
| `should_retry(attempt, exc)` | May attempt number `attempt` (1-based) be retried? |
| `delay_for(attempt)` | Seconds to wait after attempt `attempt` failed |

- `max_attempts` is the **total** number of attempts, not the number of retries.
  With `max_attempts=3` a job runs at most three times.
- The delay is geometric: `base_delay * multiplier ** (attempt - 1)`, so
  `base_delay=0.1, multiplier=2.0` gives `0.1, 0.2, 0.4, 0.8, …`.
- `max_delay` caps the delay. The cap is applied **last**, after jitter — capping
  first lets jitter push a delay back over the limit.
- `jitter` is a fraction in `[0, 1]` that scales the delay symmetrically, e.g.
  `0.5` means "within ±50%". The result is **never negative**.
- `rng` supplies the jitter randomness: any object with `random() -> float` in
  `[0, 1]`. Default it to a private `random.Random()` — reaching for the global
  module functions would make jitter untestable.
- `retry_on` with `None` means "any `Exception` is retryable". A tuple means
  "only these types". A callable is asked directly. Note a class is callable
  too, so a plain `callable(retry_on)` check misclassifies a tuple.
- `asyncio.CancelledError` and non-`Exception` `BaseException`s are **never**
  retryable: cancellation is a message to the task, not a failure to retry.
- `is_retryable` must be `False` for a non-retryable error, whatever the budget
  still allows.
- `should_retry` and `delay_for` raise `ValueError` for an attempt below 1.
- Invalid configuration raises `ValueError`: a non-positive attempt budget, a
  negative `base_delay`, a multiplier below 1 (the delay must grow, not shrink),
  a negative `max_delay`, or jitter outside `[0, 1]`.

### `jobqueue.py` — `JobQueue`

| Name | Contract |
| ---- | -------- |
| `Job(id, run)` | `run` is a zero-argument callable returning a coroutine |
| `JobResult(id, value, error, attempts)` | One outcome; `ok` is `error is None` |
| `DeadLetter(id, error, attempts)` | A job that exhausted its retryable attempts |
| `QueueClosedError` | Raised when submitting to a closed queue |
| `JobQueue(*, concurrency=4, policy=None, sleep=None, maxsize=0)` | Validate and configure |
| `submit(job)` | Accept work; `async` |
| `drain()` | Wait for every accepted job, return `list[JobResult]` in submission order |
| `shutdown()` | Drain accepted work, then refuse new work |
| `concurrency`, `policy`, `closed`, `pending`, `dead_letters` | Inspection |

- **The cap is hard.** At most `concurrency` job bodies may be in flight at any
  moment. A `concurrency` of 1 must serialise everything.
- **Nothing accepted may be lost.** A job submitted while the pool is busy still
  produces exactly one result; a job that raises must not take its worker down
  with it.
- **One result per job, not per attempt.** `attempts` on that single result is
  the total number of times the job ran.
- **Ordering.** `drain()` returns results in submission order, regardless of the
  order in which jobs finish.
- **Retries.** A retryable failure waits `policy.delay_for(attempt)` seconds —
  through the injected `sleep` — and runs again while the budget lasts. A
  non-retryable failure is never retried and is **not** dead-lettered.
- **Dead letters.** A job that exhausts its retryable attempts is dead-lettered
  exactly once, in `dead_letters`, and is never run again.
- **`shutdown()` drains.** It marks the queue closed *before* draining, so work
  submitted while it waits cannot extend it. Accepted work is completed, never
  cancelled or abandoned, and later submissions raise `QueueClosedError`.
- `pending` counts accepted jobs that have not produced a result yet.
- `maxsize` bounds the number of jobs waiting for a worker; `submit` **blocks**
  while that bound is reached, which is the backpressure that stops a producer
  from outrunning its workers. `maxsize=0` means unbounded.
- Reject `concurrency < 1` and `maxsize < 0` with `ValueError`. Default `sleep`
  to `asyncio.sleep` so tests can inject a fake clock.

### `system.py` — `JobSystem`

| Name | Contract |
| ---- | -------- |
| `JobSystem(*, concurrency=4, policy=None, sleep=None, maxsize=0)` | Build the queue and the accounting |
| `submit(name, fn)` | Accept a named job; `async` |
| `run()` | Wait for every accepted job, return `list[JobResult]` in submission order |
| `shutdown()` | Drain, then refuse new work |
| `result(name)` | The `JobResult` for `name`, or `None` |
| `results` | `dict[str, JobResult]` of finished jobs |
| `errors` | `dict[str, BaseException]` — only the failed jobs |
| `ordered_results()` | Finished results in submission order |
| `dead_letters`, `pending`, `peak_concurrency`, `closed` | Inspection |
| `stats()` | A `Stats` snapshot |
| `async with JobSystem(...)` | Shuts the system down on exit |

`Stats` carries `submitted`, `completed`, `failed`, `dead_lettered`, `attempts`,
`retries`, `pending`, `peak_concurrency` and `closed`, where:

- `attempts` is the total number of times every job ran, so
  `attempts == completed + failed + retries`;
- `retries` counts attempts that were not a job's first;
- `peak_concurrency` is the highest number of jobs that were ever in flight at
  the same time, and never exceeds the cap.

`JobSystem` owns no scheduling of its own — the queue does that — but it owns
the *bookkeeping*: job names must be unique and non-empty (a rejected job leaves
no trace in the counters), an exception must never escape `run()` or
`shutdown()`, and `Job`, `JobResult`, `DeadLetter` and `QueueClosedError` are
re-exported so callers only need this module.

## Examples

```python
policy = RetryPolicy(max_attempts=4, base_delay=0.1, multiplier=2.0, max_delay=0.5)
[policy.delay_for(attempt) for attempt in (1, 2, 3, 4)]   # [0.1, 0.2, 0.4, 0.5]
policy.should_retry(3, TimeoutError("down"))              # True
policy.should_retry(4, TimeoutError("down"))              # False
```

```python
async def main():
    async with JobSystem(concurrency=2, policy=RetryPolicy(max_attempts=2)) as system:
        await system.submit("a", lambda: asyncio.sleep(0, result=1))
        await system.submit("boom", fail)

    system.result("a")          # JobResult(id='a', value=1, error=None, attempts=1)
    system.errors               # {'boom': RuntimeError(...)}
    system.stats().completed    # 1
```

A job that always fails with a retryable error, submitted with
`RetryPolicy(max_attempts=3, base_delay=0.1, multiplier=2.0)`, runs **three**
times, asks the injected `sleep` for `0.1` and then `0.2`, returns **one**
`JobResult` with `attempts == 3`, and appears **once** in `dead_letters`.

## Constraints

- **Standard library only**: `asyncio`, `random`, `dataclasses`, `collections.abc`
  and friends. No `aiohttp`, `anyio`, `trio`, `httpx` or `requests`.
- **`retry.py` must not import `jobqueue.py` or `system.py`**, and must not sleep
  or block. `jobqueue.py` must not import `system.py`.
- **No real waiting.** Never call `time.sleep`, and never let a retry delay reach
  the real clock: every wait goes through the injected `sleep`. The suite's
  retry tests must finish in milliseconds.
- **Never busy-wait or block the event loop.** No polling loops, no spinning on
  a flag, no `while ...: pass`.
- `asyncio.CancelledError` propagates out of a job; it is not a retryable error
  and not an ordinary failure to record.
- The tests inject the clock and the RNG, so honour both seams: ignoring `sleep`
  or `rng` is a test failure, not a detail of style.

## Hints

<details>
<summary>Hint 1 — Where the concurrency cap actually lives</summary>

A counter you increment on entry and decrement on exit is not a cap: it is a
measurement. Make the bound *structural* by starting exactly `concurrency`
worker tasks that pull items off an `asyncio.Queue`. Then the maximum number of
jobs in flight is a property of the design rather than something every code path
has to remember to maintain.

If you prefer a semaphore, acquire it around the **whole** job — including its
retries — and release it in a `finally`. Releasing it after the first attempt,
or acquiring it inside the retry loop, both break the bound in exactly the way
the tests probe.
</details>

<details>
<summary>Hint 2 — Draining without losing work</summary>

`await queue.join()` on an `asyncio.Queue` waits until every item that was
`put` has had `task_done()` called for it. Wrap the body of the worker loop so
`task_done()` runs in a `finally` — otherwise a job that raises leaks a pending
item and `drain()` blocks forever.

For `shutdown()`, set the closed flag *first*, so a job submitted while you wait
cannot extend the work you just promised to finish. Then drain, and only then
stop the workers with a sentinel (`await queue.put(None)`) rather than by
cancelling tasks — a cancelled task is abandoned work, not a graceful stop.

If you spawn tasks per job instead, keep a reference to each one and `gather`
them: `asyncio.create_task(...)` without a reference can be garbage collected
mid-flight, and the job simply vanishes.
</details>

<details>
<summary>Hint 3 — One result per job, and the attempt counter</summary>

Keep the retry loop *inside* the thing that produces the result, so the loop
returns once and the caller appends once:

```python
attempts = 0
while True:
    attempts += 1
    try:
        value = await job.run()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        if policy.should_retry(attempts, exc):
            await self._sleep(policy.delay_for(attempts))
            continue
        ...
        return JobResult(job.id, None, exc, attempts)
    return JobResult(job.id, value, None, attempts)
```

Dead-letter the job when it is **retryable but out of budget**: that is the
difference between "this will never work" (fatal, one attempt, no dead letter)
and "this never recovered" (dead-lettered once). Recording a result inside the
loop instead — or retrying a dead letter — is what the tests are looking for.
</details>

<details>
<summary>Hint 4 — Retry maths without surprises</summary>

Order of operations in `delay_for`:

```python
delay = base_delay * multiplier ** (attempt - 1)
if jitter:
    delay *= 1.0 + jitter * (2.0 * rng.random() - 1.0)   # symmetric, ±jitter
delay = max(0.0, delay)                                   # never negative
if max_delay is not None:
    delay = min(delay, max_delay)                         # cap applied last
return delay
```

The `2 * r - 1` maps `[0, 1]` onto `[-1, 1]` so jitter is symmetric; using `r`
directly would only ever *increase* the delay. Note that with `jitter=1.0` the
lower bound is a multiplier of zero, which is why the `max(0.0, …)` matters.

For retryability, remember that `type` is itself a class and a tuple is not
callable: test `isinstance(exc, retry_on)` before falling back to calling
`retry_on(exc)`, or a tuple predicate will raise `TypeError`.
</details>
