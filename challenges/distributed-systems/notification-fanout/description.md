# Project: Distributed Notification Fanout

**This is a project, not a drill.** A message broker is easy to write and hard
to write correctly: the bugs that matter only appear at boundaries — a retry
that is dropped, a burst that slips past a rate limit, a circuit that never
closes again, an idempotency store that grows until the process dies.

You will build the three modules that make the delivery guarantees real. Time
is **injected**, not read from the wall clock: every policy takes a `clock`
callable returning integer milliseconds, and tests move that clock by hand. The
default clock is `monotonic_ms()`, which you must provide.

| File | Responsibility |
| ---- | -------------- |
| `channels.py` | Delivery channels: token bucket, retryable-vs-permanent errors, circuit breaker |
| `dedupe.py` | Bounded, time-windowed idempotency store |
| `fanout.py` | Orchestration: expansion, retries, outcomes, aggregate stats (entry file) |

The modules must stay separable: `channels.py` and `dedupe.py` are leaves and
must not import `fanout.py`; `dedupe.py` must not import `channels.py`.

## Your task

### `channels.py`

| Name | Contract |
| ---- | -------- |
| `monotonic_ms()` | The default clock: integer milliseconds. |
| `DeliveryError` | Base class for a refused or failed delivery. |
| `RetryableError(DeliveryError)` | A transient failure; the identical attempt may be repeated. |
| `PermanentError(DeliveryError)` | A deterministic failure; repeating it cannot help. |
| `DeliveryAttempt` | Frozen dataclass: `notification_id`, `recipient`, `channel`, `payload`, `idempotency_key`, `attempt` (1-based). |
| `TokenBucket(capacity, refill_per_second, clock=None)` | `.capacity`, `.refill_per_second`, `.tokens`, `.try_acquire(tokens=1)`. |
| `CircuitBreaker(failure_threshold=3, cooldown_ms=1000, clock=None)` | `.failure_threshold`, `.cooldown_ms`, `.state`, `.failures`, `.allow()`, `.record_success()`, `.record_failure(retryable=True)`. |
| `Channel(name, sender, *, capacity=10, refill_per_second=10.0, failure_threshold=3, cooldown_ms=1000, idempotent=True, clock=None)` | `.name`, `.sender`, `.idempotent`, `.limiter`, `.breaker`, `.send(attempt)` forwards to `sender`. |
| `CLOSED`, `OPEN`, `HALF_OPEN` | `"closed"`, `"open"`, `"half_open"`. |

**`TokenBucket`** starts full. `try_acquire` refills first, then takes the
tokens or refuses and deducts nothing. Refill is proportional to the time the
**injected** clock reports — `elapsed_ms * refill_per_second / 1000` — and never
takes the level above `capacity`. A frozen clock means a frozen bucket, however
long the process really ran. A clock that moves backwards must not mint tokens.

**`CircuitBreaker`** counts *consecutive retryable* failures. At
`failure_threshold` it opens and refuses calls until `cooldown_ms` of injected
time have passed, after which it is `half_open` and admits exactly **one** trial
call. A successful trial closes it and resets the count; a retryable failure
reopens it and restarts the cooldown. A failure recorded with `retryable=False`
is *not* evidence that the channel is down: it never opens a closed breaker and
never counts towards `failures`. `allow()` returns `False` while open, and
claims the single trial while half-open.

### `dedupe.py`

| Name | Contract |
| ---- | -------- |
| `DedupeStore(*, ttl_ms=60_000, max_size=1_024, clock=None)` | `.ttl_ms`, `.max_size`. |
| `.mark(key)` | Record `key`; return `True` if it was new, `False` if it was still known. |
| `.is_duplicate(key)` | Whether a **live** record exists. Reads must not create entries. |
| `.expires_at(key)` | The clock reading at which `key` stops counting, or `None` if it is not held or already expired. |
| `.forget(key)` | Drop one entry; return whether it was there. |
| `.purge_expired()` | Drop every expired entry; return how many went. |
| `.clear()` | Drop everything. |
| `len(store)` / `key in store` | **Live** entries only. |

Two bounds are enforced, not merely stored: an entry expires `ttl_ms` after it
was **first** recorded (a repeat hit must not extend its life, and expiry is per
entry, measured from its own insertion), and the store holds at most `max_size`
live entries, evicting the oldest to make room. Enforcing one and not the other
is the bug this module exists to prevent.

### `fanout.py`

| Name | Contract |
| ---- | -------- |
| `STATUS_DELIVERED` … | `"delivered"`, `"duplicate"`, `"failed"`, `"throttled"`, `"circuit_open"`. |
| `STATUSES` | All five statuses, in that order. |
| `Delivery` | Frozen dataclass: `notification_id`, `recipient`, `channel`, `status`, `attempts=0`, `backoff_ms=0`, `error=None`. |
| `FanoutReport` | Frozen dataclass: `notification_id`, `deliveries: tuple[Delivery, ...]`. |
| `.ok` | `True` only when **every** delivery is `delivered` or `duplicate`. |
| `.by_status()` | `dict` with a count for all five statuses, zero-counts included. |
| `.for_channel(name)` / `.for_recipient(name)` | Matching deliveries, in order. |
| `.attempts` | Total transport calls this submission cost. |
| `UnknownChannelError(KeyError)` | Raised for a channel name that was never registered. |
| `Fanout(channels=None, *, clock=None, random=None, max_attempts=3, retry_base_ms=100, dedupe_ttl_ms=60_000, dedupe_max_size=1_024)` | `.channels`, `.dedupe`, `.max_attempts`, `.retry_base_ms`. |
| `.register_channel(channel)` | Register by name and **return the channel**; a duplicate name raises `ValueError`. |
| `.channel(name)` | The channel, or `UnknownChannelError`. |
| `.unit_key(notification_id, channel, recipient)` | Static. The dedupe key of one unit of work. |
| `.notify(notification_id, payload=None, *, recipients, channels)` | Run the fanout; return a `FanoutReport`. |
| `.stats()` | Aggregate counters (see below). |

`notify` accepts a single string or any iterable for `recipients`/`channels`,
collapses repeats preserving first-seen order, and rejects an empty id, empty
`recipients` or empty `channels` with `ValueError`. Deliveries are produced
recipient-major: every channel for the first recipient, then every channel for
the second, and so on.

For each `(notification_id, channel, recipient)` unit:

1. **Dedupe first.** If the unit is recorded as done, report `duplicate` and
   send nothing. Otherwise:
2. **Circuit breaker.** If the channel refuses the call, report `circuit_open`
   with `attempts == 0`. A refused call costs no rate-limiter token.
3. **Rate limit.** If the bucket refuses, report `throttled` with `attempts == 0`.
4. **Send**, up to `max_attempts` times for an idempotent channel and **exactly
   once** for a channel with `idempotent=False`. Every attempt of a unit carries
   the same `idempotency_key`; the `attempt` field counts 1, 2, 3…
5. `PermanentError` ends the unit immediately as `failed`. A `RetryableError`
   is retried the same way, and, if every allowed attempt fails, ends as
   `failed`. Only `DeliveryError` subclasses are classified: an unexpected
   exception is a bug in the transport and must propagate, not be retried.

After each retryable failure that will be retried, add
`retry_base_ms * 2 ** (attempt - 1) + rng.randrange(0, retry_base_ms + 1)` to the
delivery's `backoff_ms`, where `rng` is the injected `random.Random`. **Never
sleep**: the caller schedules the retry, so `notify` must not advance the clock
or block.

A unit is recorded in the dedupe store **only after it actually delivered**.
A unit that failed, was throttled or was blocked stays unrecorded, so
re-submitting the same notification retries exactly the unfinished units and
reports the finished ones as `duplicate` — at-least-once without duplicating a
unit that is already done. Unknown channel names fail the submission before
anything is sent and before anything is recorded.

`stats()` returns a fresh snapshot:

```python
{
    "submissions": int,      # completed notify() calls
    "deliveries": int,       # deliveries recorded across all submissions
    "attempts": int,         # transport calls across all submissions
    "by_status": {status: int},   # all five statuses present
    "by_channel": {channel: {status: int}},  # only channels that were used
}
```

## Examples

```pycon
>>> clock = FakeClock()                       # a hand-wound clock in the tests
>>> transport = Scripted()                    # records attempts, fails on demand
>>> email = Channel("email", transport, clock=clock)
>>> fanout = Fanout([email], clock=clock, random=random.Random(1))

>>> report = fanout.notify("n1", {"text": "hi"}, recipients=["alice"], channels=["email"])
>>> [(d.recipient, d.channel, d.status, d.attempts) for d in report.deliveries]
[('alice', 'email', 'delivered', 1)]
>>> report.ok
True

>>> again = fanout.notify("n1", {"text": "hi"}, recipients=["alice"], channels=["email"])
>>> [d.status for d in again.deliveries]
['duplicate']
>>> len(transport.attempts)
1
```

| Situation | Result |
| --------- | ------ |
| Retryable failure on attempt 1, success on attempt 2 | `delivered`, `attempts == 2`, `backoff_ms > 0` |
| Permanent failure with `max_attempts=3` | `failed`, `attempts == 1` |
| Failure on one channel only | that delivery `failed`, the other `delivered`, `ok is False` |
| Capacity exhausted | `throttled`, `attempts == 0`, still retryable next time |
| Breaker open | `circuit_open`, `attempts == 0`, nothing recorded |

## Constraints

- **Standard library only.** No third-party imports beyond pytest.
- Never read the wall clock inside a policy: use the injected `clock`.
- Never `time.sleep` inside `notify`: report `backoff_ms` instead.
- No mutable default shared between instances: two `Channel`s must not share a
  bucket or a breaker, and two `DedupeStore`s must not share entries.
- Do not mutate a `FanoutReport` or let `stats()` hand out internal state.
- Neither leaf module may import `fanout.py`.

## Hints

<details>
<summary>Hint 1 — The unit of work is not the notification</summary>

One notification becomes many independently completable units. If you key
idempotency on the notification id alone, the first channel to succeed will
suppress every other channel and every other recipient — and a single dropped
retryable failure will make that suppression permanent, turning at-least-once
into at-most-once. Key on `(notification_id, channel, recipient)`, and record a
unit only after its own transport call succeeded.

</details>

<details>
<summary>Hint 2 — Refill against the injected clock, and cap it</summary>

Keep the bucket's level and the reading at which you last refilled. On every
call, compute `elapsed = clock() - last`; if it is positive, add
`elapsed * refill_per_second / 1000` tokens and clamp at `capacity`, then store
the new reading. Forgetting the clamp lets a quiet channel accrue an arbitrarily
large credit and burst far above its limit the moment traffic returns.

</details>

<details>
<summary>Hint 3 — Only the channel's own health should trip the breaker</summary>

A `PermanentError` says the payload or the address is wrong; the channel is
fine, and taking it out of service would be a self-inflicted outage. Count only
retryable failures. For the cooldown, compare the injected clock against the
reading taken when the circuit opened — and remember that `state` itself has to
apply that transition, not just `allow()`, or an open circuit is terminal.

</details>

<details>
<summary>Hint 4 — Two bounds, two mechanisms</summary>

TTL and size are not the same defence. Expiry is per entry, anchored at the
moment that entry was written, and a repeat hit must not push it out. The size
bound is enforced at insertion: evict the oldest live entry when the store is
full. Drop expired entries before you count, or the store will refuse to accept
anything new once it has filled with dead records.
</details>
