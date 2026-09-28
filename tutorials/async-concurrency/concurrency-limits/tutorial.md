# Backpressure: Semaphores, Queues and Bounded Work

Unbounded concurrency looks like a performance win until it is not: memory grows with in-flight work, your downstream dependency falls over, and tail latency collapses. Backpressure is the discipline of making the producer wait when the consumer cannot keep up, and asyncio gives you two well-tested primitives for it.

## Why unbounded concurrency is not a win

`await asyncio.gather(*[call(u) for u in million_urls])` schedules a million tasks immediately. Each task holds state — its coroutine frame, its pending result, its exception handler — so memory scales linearly with the fan-out, not with the throughput you actually achieve. Worse, all million requests hit the far end at once. A service sized for a few hundred concurrent connections will queue, then time out, then shed load, and you will observe failures whose real cause is on your side of the network.

Even when the far end survives, p99 latency degrades before throughput does: with a small pool, queueing delays stay bounded and every request finishes in roughly the same time. With an unbounded pool, most requests finish quickly and a long tail waits behind the slow ones. The honest framing is that throughput is bounded by the dependency, and unbounded fan-out converts a throughput limit into an availability incident.

## asyncio.Semaphore as a concurrency budget

A semaphore is a counter. `await sem.acquire()` decrements it and blocks when it reaches zero; `release()` increments it. Used with `async with`, it caps how many coroutines are inside the block at once.

```python
import asyncio

async def fetch_all(urls, limit=20):
    sem = asyncio.Semaphore(limit)

    async def one(url):
        async with sem:
            return await fetch(url)

    return await asyncio.gather(*(one(u) for u in urls), return_exceptions=True)
```

The subtle part is that the semaphore limits *in-flight* work, not what has been scheduled — all the tasks exist and are queued on the semaphore. That is usually fine and much simpler than a worker pool, but it does not bound memory if the input set is huge.

The other trap is construction time. A semaphore, lock or event binds itself to whichever event loop first blocks on it, and then raises `RuntimeError: ... is bound to a different event loop` when used from another loop. That bites in three places: objects created at import time and shared across tests (each `asyncio.run` is a new loop), objects cached on a module-level singleton, and objects passed into a thread that runs its own loop. Construct synchronisation primitives inside the coroutine that uses them, or ensure every loop that touches them is the same loop.

## Bounded queues with join and task_done

A bounded `asyncio.Queue` is the stronger form of backpressure: `await queue.put(item)` blocks when the queue is full, so the producer is genuinely slowed rather than merely scheduled.

```python
async def worker():
    while True:
        item = await queue.get()
        try:
            if item is None:
                return          # sentinel: this worker shuts down
            await handle(item)
        finally:
            queue.task_done()   # runs for the sentinel too
```

Three rules make the accounting work. Every `get()` must be paired with exactly one `task_done()`, including on failure and including the sentinel — the `finally` block above is what makes that true. `await queue.join()` returns only when the unfinished-task count reaches zero, so forgetting `task_done()` for sentinels hangs the pipeline forever even though all real work finished. And a worker that raises without `task_done()` in its `finally` will hang `join()` in exactly the same way; the queue is behaving correctly, the worker is not.

Sentinels are worth the awkwardness because `Queue` has no "stop" signal. Send one sentinel per worker, and never a single shared sentinel: whichever worker sees it first exits, and the others block on `get()` forever.

## Worker pools that limit in-flight work

Combining the two: a fixed number of workers consuming a bounded queue gives you a hard ceiling on concurrency, memory, and downstream load, all at once.

```python
async def run(items, width=8, maxsize=64):
    queue = asyncio.Queue(maxsize=maxsize)
    workers = [asyncio.create_task(worker()) for _ in range(width)]

    async def produce():
        for item in items:
            await queue.put(item)
        for _ in range(width):
            await queue.put(None)

    await produce()
    await queue.join()
    await asyncio.gather(*workers)
```

The ordering is load-bearing. Start the workers before producing: with a bounded queue, `await queue.put()` blocks once the buffer is full, so a producer that runs to completion first stalls forever with nobody draining the queue. Then `await queue.join()` waits for the unfinished count to hit zero, and the final `gather` collects workers that have already exited on their sentinels. Put all real items ahead of the sentinels, or a worker can shut down while items are still buffered.

When you only need a cap and simple results, the semaphore version is shorter and adequate. Reach for the queue form when you need to collect results per worker, isolate a failing item without killing the batch, or bound the amount of work buffered in memory. Choose the bound by measuring the dependency's capacity, not by picking a round number: a pool of 200 against a service that tolerates 20 in flight is just a slower way to overload it.

## Practice

Build the [bounded async worker pool](../challenges/async-concurrency-async-semaphore-pool) with a hard concurrency cap that still collects every result and every error. Then extend it to the [job queue project](../challenges/async-concurrency-async-job-queue), where retries and a dead-letter queue make the failure paths the interesting part. Test the bound explicitly — assert the observed maximum in-flight count, and assert that a hung worker does not stop the other workers from finishing.
