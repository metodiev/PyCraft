# Caching: Layers, Invalidation and Staleness

A cache is a copy of data that is permitted to be wrong for a bounded time.
Once you state it that way, caching stops being a performance trick and becomes
a correctness decision with a budget attached.

## Where caches live

Each layer can see different things, and that limits what it can be trusted
with.

| Layer | Sees | Must not be trusted with |
| ----- | ---- | ------------------------ |
| Client | One user, the URL, response headers | Data changed by another user; anything you cannot expire |
| CDN / reverse proxy | URL and request headers, shared across users | Private responses, unless `Vary` and `Cache-Control: private` are set correctly |
| Application (in-process or Redis) | Your domain model; you control keys and eviction | Correctness by itself — it is your job to invalidate it |
| Database buffer pool | Pages, not rows | Anything, but it explains why the first run of a query is slow |

A materialised view is also a cache: a query result with an explicit refresh
step. Treat it with the same questions — what is the staleness budget, and who
triggers the refresh?

## Cache-aside, write-through, write-behind

**Cache-aside** is the default: read the cache, on a miss read the source and
populate. Simple, and it tolerates a cache outage because the source still
answers. The cost is that the write path must invalidate deliberately.

**Write-through** updates the cache and the store in the same synchronous
operation. Reads rarely miss; writes pay for two systems and need the same
ordering discipline as any distributed write.

**Write-behind** writes the cache first and flushes to the store later. Writes
are fast and a crash loses acknowledged data. Use it only where loss is
survivable.

Ordering is where cache-aside goes wrong. Delete the key *after* the commit, not
before: between an early delete and the commit, a concurrent reader can miss,
load the old value, and repopulate the stale entry with a fresh TTL. Deleting
after the commit narrows the race but does not remove it; a versioned key or a
short TTL is what finally closes it.

## TTL is a staleness budget

A TTL is not a knob to tune, it is a statement of how wrong you allow the data
to be. A price that is wrong for ten seconds costs money; a product description
that is wrong for an hour does not. Derive the number from that sentence rather
than from a benchmark.

Never give a large group of keys the same TTL. If a batch of writes repopulates
ten thousand keys together, they expire together and the next requests all miss
at once — synchronised expiry, the trigger for a stampede. Jitter the value:

```python
import random

def ttl_with_jitter(base: float) -> float:
    return base + random.uniform(0, base * 0.2)
```

## The two hard problems

**Invalidation** is hard because you cannot enumerate everything that depends on
a value; it may be embedded in a rendered page, a search index or a report. The
practical answer is *key versioning*: put an entity generation number in the key
so a single counter bump orphans the whole namespace at once, with no delete
sweep and no scan. Combine it with TTLs as a backstop for the keys you forgot.

**Stampede** is many callers missing on the same key at the same moment and all
recomputing. Single-flight collapses that to one computation, with the others
waiting on the same lock and reading the fresh value:

```python
import threading
import time


class SingleFlight:
    def __init__(self, load, ttl=30.0):
        self._load, self._ttl = load, ttl
        self._lock = threading.Lock()
        self._value, self._expires = None, 0.0

    def get(self, key):
        with self._lock:
            if self._value is None or time.monotonic() >= self._expires:
                self._value = self._load(key)
                self._expires = time.monotonic() + self._ttl
            return self._value
```

Holding the lock during recomputation makes every other caller wait, which is
the point, but it also means a slow loader serialises traffic; bound the load
with a timeout, and prefer returning a slightly stale value to blocking
indefinitely. Related defences: *probabilistic early expiry*, which refreshes
just before expiry with rising probability, and *negative caching*, which
remembers "not found" so a missing row cannot be turned into a query flood —
give negative entries a short TTL, because absence is often temporary.

## A cache is a correctness decision

Removing a cache should not change observable behaviour. If it does, the cache
is part of your semantics and must be tested like one: run the suite with the
cache disabled, and check that every cache key includes every input that can
change the answer — user, locale, feature flags, permissions. A key that omits a
dimension does not merely serve stale data; it serves another user's data. That
is a security defect, not a latency trade-off.

## Practice

Use the [REST API Service challenge](../challenges/backend-engineering-rest-api-service)
to add a cache deliberately: pick a TTL and justify it as a staleness budget,
version the keys, and prove the API still behaves correctly with the cache
cleared between requests.
