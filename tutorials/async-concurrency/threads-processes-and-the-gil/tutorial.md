# Threads, Processes and the GIL

The GIL is a single mutex that lets only one thread execute Python bytecode at a time. It does not make threads useless, and it does not make processes free — it just forces you to identify what your workload is actually waiting on before choosing a concurrency model.

## What the GIL does and when it is released

CPython reference-counts every object, and without the GIL two threads could decrement a refcount simultaneously and free the same object twice. The GIL is the cheap, coarse solution: one lock protecting the interpreter state.

It is released in two situations that matter:

- Around blocking I/O. The socket layer, file I/O, `time.sleep` and similar calls drop the GIL for the duration of the call, so another thread can run Python bytecode while the first thread waits.
- Inside C extensions that explicitly release it — NumPy array operations, database drivers, compression libraries, `hashlib` for large inputs, and so on.

It is *not* released for pure-Python computation, except that the interpreter checks periodically whether another thread wants the lock — every `sys.getswitchinterval()` seconds, 5 ms by default. So threading gives you concurrency for I/O-bound work and context-switch overhead for CPU-bound work, never parallel speedup.

<details>
<summary>What about free-threaded CPython?</summary>

CPython 3.13 and later ship an experimental free-threaded build (PEP 703) in which the GIL can be disabled; the standard build still has it, and that is what virtually every deployment runs today. Until the free-threaded build is the default on your target runtime, design as if the GIL is present. It is the conservative assumption, and code that is correct under the GIL stays correct without it — with the caveat that data races you previously got away with may now surface.
</details>

## ThreadPoolExecutor versus ProcessPoolExecutor

`concurrent.futures` gives both models the same API, which hides a large difference in cost.

```python
from concurrent.futures import ProcessPoolExecutor, ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=16) as pool:
    texts = list(pool.map(load_page, urls))       # I/O-bound: GIL released while waiting

with ProcessPoolExecutor() as pool:
    digests = list(pool.map(hash_chunk, chunks))  # CPU-bound: real parallelism
```

`ThreadPoolExecutor` passes arguments by reference and shares memory, so submitting a large object costs nothing. `ProcessPoolExecutor` pickles every argument, sends it through a pipe, and pickles the result back. That cost is per call, and it is often the reason a naive process pool is slower than the single-threaded version for small payloads. Processes also cannot share mutable state: a global counter incremented in a worker stays in the worker's memory, and only what you return comes back.

Pickling imposes a hard constraint on what you can submit, and the failure mode is a `PicklingError` before the child process even starts.

```python
from concurrent.futures import ProcessPoolExecutor

def total(rows):            # module-level function: picklable by name
    return sum(rows)

with ProcessPoolExecutor() as pool:
    results = list(pool.map(total, chunks))
    pool.map(lambda rows: sum(rows), chunks)   # PicklingError
```

If you need to move large arrays between processes, `multiprocessing.shared_memory` or a NumPy memmap avoids the copy; otherwise keep the payload small and the chunks large, so serialization is a small fraction of the work.

## Shared state, races, and why `+=` is not atomic

Threads share everything, which is the point and the hazard. `counter += 1` compiles to a load, an add and a store. A thread can be switched out between the load and the store, so two increments can produce one increment — a classic lost update, and the same anomaly transactions face.

```python
import threading

lock = threading.Lock()
counter = 0

def bump():
    global counter
    with lock:
        counter += 1
```

Use a lock whenever a read-modify-write spans a bytecode boundary, and prefer `queue.Queue` over a hand-rolled list plus condition variable — the queue's synchronisation is already correct. Note that `list.append` and `dict[key] = value` are individually atomic under the GIL in CPython, but relying on that is brittle: it is an implementation detail, and it does not extend to check-then-act sequences like `if key not in d: d[key] = compute()`.

Deadlock is the second cost. Always acquire locks in a single global order, use timeouts (`lock.acquire(timeout=...)`) where you can, and never call out to unknown code — a callback, a user-supplied hook — while holding a lock.

## When asyncio beats threads

Threads are heavier: each one reserves a stack (commonly 8 MB of virtual address space on Linux, though it is lazily faulted), and every hand-off is a real OS context switch subject to the scheduler. A few thousand threads is a practical ceiling; tens of thousands of asyncio tasks are routine because they are heap objects driven by one thread. Asyncio also makes cancellation, timeouts and backpressure first-class, whereas cancelling a thread is not supported at all in Python.

Choose asyncio when the work is I/O with high fan-out and your libraries are async-native, or when your libraries are synchronous but you can wrap calls in `asyncio.to_thread`, which is the standard bridge from sync to async. Choose threads when the work is blocking I/O through sync-only libraries with modest concurrency. Choose processes when the work is CPU-bound. The honest answer for most real systems is a process pool for the compute, asyncio for the network, and threads only inside libraries that demand them.

## Measure which bound you have

Do not guess. Run the workload once and watch CPU utilisation and wall time: if CPU stays near one core while wall time grows, you are CPU-bound single-threaded and want processes. If CPU is low and time is spent waiting on I/O, you are I/O-bound and threads or asyncio will help. If CPU is split across several processes already, look for the contention — often a lock, a shared connection, or a serialization bottleneck on one resource — rather than adding workers.

## Practice

Apply this in the [asynchronous job queue project](../challenges/async-concurrency-async-job-queue): it uses asyncio for scheduling, and the retry and dead-letter paths show why a bounded worker pool with explicit failure handling beats a thread explosion. Then time the same CPU-bound task with a thread pool and a process pool and observe the difference for yourself.
