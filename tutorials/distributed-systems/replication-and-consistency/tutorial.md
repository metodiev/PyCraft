# Replication, Quorums and Consistency Models

Replication is not a feature you enable; it is a trade against a specific failure. You copy data so that losing one machine does not lose it, and so reads can be served from somewhere nearby. Once there is more than one copy, every read is a choice about which copy may answer — and every consistency model is a statement about how much that choice can hurt.

## Pick the topology for the failure you have

**Single-leader.** One node accepts writes and streams them to followers. It is the easiest to reason about: writes are totally ordered by the leader, so there are no write conflicts to resolve. Its weakness is the leader itself — failover takes time, an unreachable leader means writes stop, and a partitioned old leader may still believe it is in charge and accept writes that the new leader overwrites. Optimised for correctness within one failure domain and a fast, unambiguous failover.

**Multi-leader.** Several nodes accept writes, typically one per region. It optimised for write availability and latency across geographies: a client writes to its local leader. In exchange you must resolve conflicts, because two leaders can accept concurrent writes to the same key and neither is "the" one. Last-write-wins discards data silently; counters double-count; sets need a mergeable representation such as a CRDT.

**Leaderless.** Any replica accepts a write, and the client or a coordinator writes to several and reads from several. It optimised for availability under partition and for having no special node, at the cost of moving conflict resolution and repair into your application. This is how Dynamo-style stores and quorum-based systems work.

Name the failure first. If the answer is "a machine dies", single-leader plus a healthy failover path is usually the cheapest correct design. Multi-leader pays for itself only when cross-region write latency is a real user-visible cost.

## What a quorum buys

With `N` replicas, a write acknowledged by `W` of them and a read served by `R` of them, the condition `R + W > N` guarantees that the read set and the write set intersect: at least one replica in every read quorum has seen the write. That is the entire claim, and it is exactly a claim about overlap — it is not "the read returns the newest value". Things it does not buy:

- It does not order concurrent writes; two writes that overlap in time may be acknowledged by disjoint quorums, and you still need versioning or a conflict rule to pick a winner.
- It assumes replicas that were in the quorum have not since lost the data. A node that acked a write and then rolled back a disk failure breaks the arithmetic unless it rejoins through a repair path that reconciles rather than trusts local state.
- The arithmetic assumes live replicas. If you keep quorum sizes configured for five replicas while only three are running, a write quorum of three is every live node, and one more failure stops you accepting writes.
- If a read repair or hinted handoff path is buggy, quorums still hold on paper and fail in practice.

The usual configuration `W = R = 3` with `N = 5` tolerates two failures in both directions and costs the latency of the third-fastest replica per operation. `W = 1, R = N` is fast to write and fragile to read; `W = N, R = 1` is the reverse.

## Synchronous, asynchronous, and the lag window

**Synchronous** writes wait for replicas to acknowledge before returning; the cost is on the write path, measured by the slowest required replica. **Asynchronous** writes return as soon as the leader has them locally, and followers catch up later. There is always a window — microseconds under normal load, seconds or minutes during a backlog — in which a write is committed but not visible elsewhere. Many systems are semi-synchronous: wait for one follower, lag the rest.

That window is the source of the classic bug report. A user saves their profile, the browser reloads, the reload is routed to a replica that has not received the update, and the user sees the old value. Nothing is broken — the write committed, and the read was served by a copy that is behind. The system behaves correctly under a weaker guarantee than the user assumes.

The defensible answer is not "eventual consistency" as an explanation to a user. It is to choose a *session* guarantee that matches what the user is doing and enforce it on the read path.

## Session guarantees you can hand to a user

- **Read-your-writes**: after a client writes, its subsequent reads see the write. Options: route that client's reads to the leader briefly, carry the write's log position (an LSN or version) in a session cookie and require replicas to be at least that current, or pin the session to the replica that acked the write. Each has a cost — leader reads do not scale, position tracking needs replicas to report their position.
- **Monotonic reads**: a client never sees the state go backwards. If a session is pinned to a replica, a failover or load-balancer reshuffle can silently move it to a lagging copy and produce a value older than one already shown. Carrying the last-seen version and rejecting replicas behind it fixes this; the session must then tolerate a retry against a fresher replica.
- **Monotonic writes**: a client's writes are applied in the order it issued them — important when the same session edits one record in sequence.
- **Consistent prefix**: readers never see an effect without its cause.

These are cheap relative to global consistency because they constrain only what one session observes, not what the whole cluster may do.

## Eventual consistency is a promise about time

It says that if writes stop, replicas converge — with no bound on when. That is a useful statement about durability, not a licence to return nonsense. Returning a value that was never written, or mixing values from different points in a transaction, is not a lag artefact; it is a bug. Convergence needs a defined conflict rule, a repair mechanism, and — if the application compares timestamps across machines — a note that clocks disagree, which is why version vectors exist as an alternative to wall time.

## Practice

Replication choices bite hardest where they meet delivery and retries. [Distributed Notification Fanout](../challenges/distributed-systems-notification-fanout) puts per-channel deduplication, rate limiting and a circuit breaker in one fanout path, which is where these guarantees stop being theoretical.
