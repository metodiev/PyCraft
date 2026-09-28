# Messaging and Work Queues: Delivery Semantics

A queue is a promise about the future: the work will happen later, possibly
more than once, possibly out of order. Design starts by deciding which of those
adverbs your workflow can tolerate.

## Why work leaves the request path

Four reasons justify a queue. **Latency** — the user waits for an
acknowledgement, not for the work. **Failure isolation** — a slow email provider
no longer fails a checkout. **Retry** — a queue can redeliver; an HTTP request
retried by a client cannot. **Burst absorption** — the backlog is a buffer, and
consumers drain it at their own rate.

The price is that the request can no longer report the final outcome. It returns
`202 Accepted` and a status resource, and every consumer-visible failure now
needs a state machine and an operator story. Duplicate deliveries become a real
failure mode rather than a theoretical one.

## Which delivery guarantee you can actually build

**At-most-once** dispatches and never redelivers. Messages are lost when a
consumer dies mid-flight. Acceptable for metrics, never for payments.

**At-least-once** acknowledges only after the handler finishes. If the broker
does not see an acknowledgement, it redelivers. This is the standard guarantee,
and it is what you should assume for any work queue.

**Exactly-once** is not achievable end to end. Brokers that advertise it mean
their own transactions and deduplication between producer and broker; the
moment your handler sends an email or calls a third-party API, the outside
world has no idea a redelivery was a duplicate. What you build instead is
**effectively-once**: at-least-once delivery, plus an idempotent handler, plus a
deduplication record keyed by message id. The deduplication write must commit in
the same transaction as the effect — otherwise a crash between the two either
loses the work or repeats it.

## Acknowledgement, redelivery and dead letters

A visibility timeout hides a message while one consumer works on it. No
acknowledgement before the timeout expires and the message becomes visible to
another consumer. The classic bug is work that routinely exceeds the timeout:
the same job runs twice, concurrently, with neither consumer knowing. Set the
timeout above the p99 of the work, heartbeat to extend the lease for long jobs,
and make the handler idempotent anyway, because a lost acknowledgement after
successful processing is indistinguishable from a crash.

Acknowledge after the effect, never before. Ack-first turns a crash into silent
data loss.

A message the handler can never process — an unparseable payload, a null it does
not expect, a bug triggered by one input — will be redelivered forever. It
consumes capacity, and on an ordered queue it blocks everything behind it. The
defence is a retry ceiling: after `maxReceiveCount` attempts the broker routes
the message to a dead-letter queue.

Treat the DLQ as a holding area rather than a bin. Alert on its depth, record
the failure reason and the delivery count, and redrive after a fix is deployed.
Distinguish retryable failures (timeout, `503`, lock contention) from permanent
ones (schema violation, unknown entity) and fail fast on the permanent class so
the retry budget is not spent on noise.

## Ordering

Global ordering costs throughput: it means one consumer at a time, or a single
partition. What queues actually offer is per-key ordering — everything with the
same partition key (for example `order_id`) is delivered in order, and there is
no ordering between keys. That is usually enough, and it is the guarantee to
design against.

Retries reorder even within a partition. A message that is redelivered after a
failed attempt arrives after newer messages on the same key. If ordering
matters, either park the partition (head-of-line blocking, and one poison
message stalls the key) or make transitions monotonic: store a version and apply
an update only when it is newer than what is already stored. The second option
is almost always the better trade.

## Duplicate delivery reaching a non-idempotent handler

Consider a "record the order" consumer that increments a counter and sends a
receipt. A redelivery after a crash-before-ack now increments twice and sends
two receipts. The customer sees two emails and the metric says two orders — and
nobody notices until reconciliation.

Standard defences:

- upsert on a natural or message-derived key, so a repeat overwrites rather than
  appends;
- conditional writes — `UPDATE ... WHERE version < :version` — so the second
  application is a no-op;
- insert a processed-message row with a unique constraint, catch the violation
  and drop the duplicate.

Choose based on the effect. Database writes can be made conditional; outbound
side effects cannot, so either move them behind the same deduplication check or
make them naturally idempotent (a send with a stable idempotency key).

## Practice

Take the [REST API Service challenge](../challenges/backend-engineering-rest-api-service)
and move one slow side effect off the request path: return `202` with a status
resource, make the consumer idempotent under duplicate delivery, and decide what
the queue should do after three failed attempts at the same message.
