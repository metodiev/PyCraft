# Idempotency: At-Least-Once Means You Must Deduplicate

Exactly-once delivery is not achievable over a network that can lose an acknowledgement. The sender writes a request, the receiver performs it, the response is lost in flight — and the sender cannot tell that case apart from "the request never arrived". It must retry, and a retry of a non-idempotent operation is a second effect. The achievable target is at-least-once delivery plus deduplication, which yields *effectively-once*: the effect happens once even though messages may be delivered more than once.

## Why the third outcome forces the problem

A remote call has three outcomes: success, and no answer. The third is the one that matters, because it is indistinguishable from failure at the call site. Any protocol that claims exactly-once is either keeping state on the receiver to detect the duplicate (which is deduplication, whatever you call it) or it is silently dropping work. Choose the former and make it explicit.

## Idempotency keys

The standard design for an API: the caller generates a key that identifies the *logical* request, and sends it with the request. The server stores the key together with the outcome, and on a repeat of the same key returns the stored outcome instead of re-executing.

```python
def charge(idempotency_key, amount, store):
    existing = store.get(idempotency_key)
    if existing is not None:
        return existing                      # replay: return the original result
    try:
        result = gateway.charge(amount)
    except PermanentError as exc:
        store.put(idempotency_key, outcome=exc.error, status="failed")
        raise
    store.put(idempotency_key, outcome=result.id, status="succeeded")
    return result
```

The details are where implementations break:

- **Store the result, not just the key.** Recording "seen" and returning an error on the second call turns a retry into a failure the caller cannot distinguish from a real one. The retry must be able to learn what happened.
- **Insert the key before doing the work, in the same atomic step if possible**, so two concurrent retries cannot both pass the check. A unique constraint on the key column does this for you; a read-then-write does not.
- **Scope the key.** Uniqueness must cover the caller and the operation, or two clients that each pick `"1"` collide.
- **Give keys a lifetime** and be honest about it. Expiring a key after 24 hours means a retry after 24 hours duplicates the effect; pick the window to exceed the caller's maximum retry horizon, and remember that a queue with a long delivery timeout can exceed it.
- **Handle concurrent in-flight requests.** A retry arriving while the first attempt is still running should block, wait, or return a defined "in progress" result — not start a second execution.
- **Derive the key deterministically** where possible. A random uuid per attempt is not an idempotency key; a hash of the logical request (account, amount, invoice id) is.

## Idempotent write patterns

Where you control the write, choose a pattern that is naturally repeatable:

- **Upsert**: `INSERT ... ON CONFLICT DO UPDATE SET payload = excluded.payload`. Repeating it converges to the same row.
- **Conditional update**: `UPDATE ... WHERE version = 7`. The second application matches zero rows and reports that it did not apply, which is the information you need. Beyond deduplication this is optimistic concurrency control — it is also what stops a retry from overwriting a newer edit.
- **Set rather than increment**: an absolute value assignment repeated any number of times is the same as one assignment. This is the single most valuable habit when designing for retries.
- **Derived keys**: name the record after the logical event (`notify-{message_id}-{channel}`) so a second delivery writes the same row rather than a new one.

Operations that accumulate damage when repeated are the ones to redesign: `balance = balance + 10`, `append` to a log, `count += 1`, sending an email. Each needs either a deduplication store or a natural key that makes the second attempt a no-op.

A useful sanity check: for any handler, ask what happens if it is invoked twice with the same input, and once more concurrently with itself. If the answer is "the same state", the handler is idempotent. If "one more unit of whatever", it needs a key.

## A retry is not a new logical request

This distinction causes most of the real incidents. If a caller retries with a fresh key, the server sees two distinct logical requests and correctly performs the effect twice — the deduplication you built never gets a chance. So retry logic and key generation must be linked: the key is created once per logical intent, before the first attempt, and reused for every attempt. That usually means the key has to survive process restarts: generate it and persist it with the outbox row, not inside the retry loop.

The same rule applies to the receiver's view of a queue. A message redelivered with the same message id is a retry; the same *content* under a new id is a new request. Dedup on the identifier the producer controls, and make that identifier mean the logical event rather than the attempt.

## Deduplication has a cost, so scope it

A persistent per-message store is correct and grows without bound unless it is trimmed. Practical scoping:

- Deduplicate at the point where the effect is non-idempotent, not on every hop. If the effect is an upsert, its natural key is already the deduplication.
- Partition the store by key and prune by age. A time-windowed set of seen ids is enough when duplicates can only arrive within the retry horizon; a duplicate outside that window is indistinguishable from a legitimate re-send.
- Never deduplicate on the *result* of a hash of mutable payloads unless you actually want "same content, same effect" semantics.

The failure mode to avoid in the other direction is a deduplication store that silently drops work: if it is unavailable and the handler treats that as "already seen", you have traded duplicates for losses, which is far worse for almost every business case. Fail closed on the effect, not on the record.

## Practice

[Distributed Notification Fanout](../challenges/distributed-systems-notification-fanout) is built around this: a fanout where a retryable failure is never dropped, a finished unit is never re-sent, and the report must not claim success for work that was left unfinished. Getting the deduplication window and the retry classification right is most of the problem.
