# Trade-off Analysis: CAP, PACELC and Honest Choices

Distributed systems do not have best options, only options with different failure behaviour under load and under partition. The skill is not picking the "right" side of a trade-off — it is describing the choice precisely enough that the consequences are visible before they arrive.

## Partition tolerance stops being optional once you partition

CAP is usually quoted as "pick two", which is misleading. Once a system spans more than one machine, a network partition is not a configuration choice; it is something the network will do to you eventually. The real content of CAP is narrower and more useful: *while* a partition is happening and the replicas cannot talk, a system either refuses the operation or accepts it while the two sides disagree.

- Refusing writes preserves consistency: callers see an error, and no one sees a value that will later be contradicted.
- Accepting writes preserves availability: callers see success, and the system owes a reconciliation later — last-write-wins, a merge function, or a conflict surfaced to a human.

Neither is "correct". A payment ledger generally refuses. A like counter generally accepts and converges later. What matters is that the choice was made before the partition, not discovered during it.

## PACELC: the other 99.9% of the time

Partitions are rare; normal operation is not. PACELC extends the framing: if there is a partition, choose availability or consistency; **else**, choose latency or consistency. Replication in the normal case is a latency-versus-consistency dial. A quorum write waits for a majority of replicas before it returns, and a quorum read is guaranteed to see it. An asynchronous write acknowledges on one replica and returns sooner, and readers may see data one replication lag behind.

The same database can be on both sides of this dial per operation. A single-node read of the primary is the consistent, slower choice; a read from a lagging replica is the faster, staler choice. Which one you want depends on the screen the user is looking at.

## Consistency is chosen per operation, not per product

"We chose consistency" is almost never true for a whole product. Consider an order service:

- Writing an order commits to a quorum of replicas before responding — availability is sacrificed for correctness of money.
- Order history is read from an asynchronous replica — latency is preferred, and a few seconds of lag is invisible to a user refreshing the page.
- The product catalogue is cached for sixty seconds — staleness is bounded by design, and a price change propagating a minute late is acceptable.

Three operations, three different answers, and a defensible product. The failure mode is not mixing choices; it is being unable to say which choice applies where when a support engineer asks why two users see different order counts.

## Write it down so it is a decision, not an accident

A trade-off record is short: what was decided, why, what was rejected, and what would trigger a revisit.

```text
Decision: order writes commit to a quorum; reads of order history may
          serve from an asynchronous replica, with lag held under 5 s.

Context:  p99 write latency budget is 200 ms; audit rules require that a
          confirmed order is never lost.

Rejected: (a) single-primary sync replication — too slow across regions.
          (b) async writes everywhere — a confirmed order could vanish.

Consequences: history can lag by seconds; support tooling must read the
          primary to answer "did this order exist?".

Revisit if: read-your-writes complaints exceed 1% of tickets, or the
          replica lag p99 exceeds 5 s for two consecutive weeks.
```

The rejected options are the most valuable section. Six months later, someone will propose the option you already discarded, and the record answers them with the context that made it a bad idea — or reveals that the context has changed and the decision should be revisited.

Two habits keep these records honest. First, name the metric that would falsify the decision, as above; a decision with no falsifier is a preference. Second, attach the choice to a user-visible behaviour, not to an internal label. "We are eventually consistent" tells nobody anything; "the feed may show a post you deleted up to thirty seconds ago" tells a support engineer exactly what to say.

## Practice

[Replicated Log with Quorum Replication](../challenges/system-design-replicated-log) makes you implement the consistent side of this dial: quorum writes, term-monotonic leadership and convergence after a partition heals. While you build it, write the trade-off record for the paths you leave intentionally weaker — commit index visibility, follower reads and what happens to an in-flight write when the leader falls over.
