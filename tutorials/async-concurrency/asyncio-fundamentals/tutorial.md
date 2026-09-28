# asyncio: The Event Loop, Tasks and await

`asyncio` gives you concurrency on a single thread: one event loop, many coroutines, each running until it hits an `await` and yields control. Almost every asyncio bug is a misunderstanding of when control returns to the loop and what happens to the work while it is gone.

## Concurrency is not parallelism

Parallelism means two lines of code execute at the same instant, which needs two cores. Concurrency means two tasks are in progress at once while only one is running at any instant. `asyncio` provides the second: the loop runs one coroutine until that coroutine awaits something that is not ready, then switches to another.

That is why asyncio is excellent for I/O-bound work — waiting on sockets, files, subprocesses — and useless for CPU-bound work, which never awaits and therefore never lets anyone else run. Keep this framing: the loop is a scheduler, not a source of extra compute.

## Coroutines, tasks and futures

A coroutine function is declared with `async def`. Calling it does not run it; it returns a coroutine object that must be awaited or scheduled.

```python
async def fetch(url):
    ...

fetch("https://example.com")          # nothing has happened yet
await fetch("https://example.com")    # now it runs, inline, in this task
task = asyncio.create_task(fetch("https://example.com"))  # scheduled on the loop
```

A `Task` wraps a coroutine and registers it with the loop so it can be driven independently — this is what makes concurrency possible. A `Future` is the lower-level primitive a task uses to report a result or exception; most application code should deal in tasks and `await` them rather than constructing futures directly.

Forgetting the `await` is the classic mistake. Since the call returns a coroutine object silently, the code runs, no exception is raised, and the work simply never happens — often surfaced as `RuntimeWarning: coroutine 'fetch' was never awaited`. Treat that warning as a bug, and configure your test suite to fail on it.

## await yields control — and interleaving is observable

Ordering follows from where the yields are. Two tasks that each do one slow `await` interleave at exactly that point; code before the first await runs to completion without interruption.

```python
async def worker(name):
    print(f"{name} start")
    await asyncio.sleep(1)
    print(f"{name} end")

async def main():
    await asyncio.gather(worker("a"), worker("b"))
```

This prints `a start`, `b start`, `a end`, `b end` — both starts run before either sleep completes. Any state you mutate before an `await` is visible to other tasks when they run, which is why asyncio code still needs care around shared mutable state, even without threads.

## gather versus as_completed

`asyncio.gather` waits for all the awaitables and returns results in the order you passed them, regardless of completion order.

```python
results = await asyncio.gather(*[fetch(u) for u in urls])
```

`asyncio.as_completed` yields awaitables as they finish, so you can process results in completion order and start consuming before the slowest task is done.

```python
for coro in asyncio.as_completed([fetch(u) for u in urls]):
    result = await coro
```

Choose based on whether you need the whole set or incremental progress. Both fail fast by default: if one task raises, `gather` propagates that exception while the others keep running in the background unless you cancel them. With `gather(..., return_exceptions=True)` failures come back as values in the results list, which is usually what you want in a pipeline that must report per-item errors — the same shape the [job queue challenge](../challenges/async-concurrency-async-job-queue) expects. `gather` accepts coroutines, tasks and other awaitables; passing a plain value raises `TypeError` at submission time. Wrapping coroutines in tasks first makes cancellation explicit and is worth doing whenever partial failure is possible.

## Blocking the loop, and cancellation

A CPU-bound call inside a coroutine blocks everything. There is no preemption: while `time.sleep(5)` or a tight numeric loop runs, no other task is scheduled, no timeout fires, and health checks fail. The fixes are to move the work to a thread or process (`await asyncio.to_thread(cpu_or_blocking_fn)`, `loop.run_in_executor`) or to split it into chunks that yield between them.

Cancellation arrives as a `CancelledError` raised inside the task at its current await point. It is not an exception you should swallow: catch it only to clean up, then re-raise. Since Python 3.8 `CancelledError` derives from `BaseException`, so `except Exception:` no longer catches it — but a bare `except:` still does, and that silently breaks timeouts and shutdown. Worse, a task that suppresses a cancellation keeps running, and `asyncio.wait_for` will not rescue you: when the deadline passes, `wait_for` cancels the inner task and waits for it. A task that ignores the cancel therefore makes the timeout late rather than fatal: a coroutine that caught the cancellation and then awaited a second-long sleep made `wait_for` return normally 1.1 seconds after a 0.1-second deadline, with no `TimeoutError` raised at all. Do not treat cancellation as advisory in any code you expect to be timed out or shut down.

## Practice

The [asynchronous job queue project](../challenges/async-concurrency-async-job-queue) puts all of this together: scheduled tasks, retries, and shutdown that cancels cleanly. Build a small example first — run three `fetch`-style coroutines with `gather`, then with `as_completed`, and confirm you can predict the print order. Once you can, [Backpressure: Semaphores, Queues and Bounded Work](../tutorials/async-concurrency-concurrency-limits) is the natural next step.
