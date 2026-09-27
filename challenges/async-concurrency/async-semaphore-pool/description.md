# Bounded Async Worker Pool

`asyncio.gather` will happily open ten thousand sockets at once. Real services
cap concurrency — a pool of N workers draining a queue — and they must still
return one result per job, in order, while keeping every error where the caller
can see it.

## Your task

Implement `async def run_pool(jobs, workers)`.

* `jobs` is a **synchronous iterable** of zero-argument callables, each returning
  a coroutine (e.g. `functools.partial(fetch, url)` or `lambda: work("a")`).
  It may be a generator and may be huge — do not materialise it into a list.
* `workers` is a positive `int`; anything else raises `ValueError`.
* Return a `list` of `(index, result_or_exception)` pairs **in job order**,
  where index is the 0-based position in `jobs`.
* Jobs run **lazily**: a new job is only started when a slot is free, and the
  pool never has more than `workers` coroutines in flight at once.
* A job that raises produces its exception object in the result list rather than
  cancelling siblings. Cancellation of the pool itself (`asyncio.CancelledError`)
  must propagate, not be captured.
* Each job's callable is invoked exactly once, inside the pool.
* The pool finishes when `jobs` is exhausted, even if `jobs` is an iterator that
  never ends *while* workers are busy — a slow generator must not stall the pool.

## Examples

```python
async def double(n):
    await asyncio.sleep(0)
    return n * 2

await run_pool([lambda: double(1), lambda: double(2)], 1)
# [(0, 2), (1, 4)]

async def boom():
    raise ValueError("no")

await run_pool([lambda: double(3), boom], 4)
# [(0, 6), (1, ValueError("no"))]
```

## Constraints

* Standard library only: `asyncio` and `contextlib` are fine.
* Do not use `asyncio.Semaphore` *and* ignore it — the cap is measured by the
  tests, which track how many jobs are simultaneously inside their body.
* Errors are returned, never raised (except `CancelledError`, which is not an
  `Exception` subclass anyway — but do not swallow it explicitly either).
* `run_pool` must not block the event loop: no `time.sleep`, no busy waiting.

## Hints

<details>
<summary>Hint 1 — A worker loop per slot</summary>

Spawn `workers` consumer tasks that pull from a shared `asyncio.Queue`. Stop them
with a sentinel rather than cancellation, and remember the loop needs to be
primed before the first `await` on the queue:

```python
queue = asyncio.Queue(maxsize=workers * 2)
results = {}

async def worker():
    while True:
        item = await queue.get()
        if item is None:
            return
        index, job = item
        results[index] = (index, await _settle(job))
```

The `maxsize` is real backpressure: the producer blocks instead of pulling the
generator faster than the workers can keep up.

</details>

<details>
<summary>Hint 2 — Capturing without swallowing cancellation</summary>

```python
async def _settle(job):
    try:
        return await job()
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        return exc
```

`asyncio.CancelledError` inherits from `BaseException` in 3.8+, so catching
`Exception` already spares it — but be explicit if that makes the intent
clearer. Feed the queue from a producer task while the main coroutine awaits the
workers, so a slow generator cannot deadlock the queue.
</details>
