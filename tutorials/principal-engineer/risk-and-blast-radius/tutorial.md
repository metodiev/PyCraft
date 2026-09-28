# Risk, Blast Radius and Fault Isolation

Every component will fail; the design question is what fails with it. Blast radius is the answer to that question, and shrinking it is usually more valuable than making any single component more reliable, because it bounds the damage instead of reducing the odds.

## Blast radius as a question

Ask it in the form of a sentence about failure, not about design: *when this fails, what else fails with it?*

If the answer is "one customer's background jobs", the design is bounded. If it is "the entire API for everybody", you have a single point of failure regardless of how many replicas you run, because the replicas are replicas of the same failure. Replicas protect against hardware death; they do nothing against a poison payload, a lock held by one tenant's batch job, or a code path that only one customer's data reaches.

The useful output of asking the question is a list of the shared things. Blast radius is usually not set by the shape of the service diagram; it is set by what the services share.

## Reduce it along independent axes

Isolation is worth doing at several layers at once, because they fail differently.

Cellular architecture partitions the workload so that a cell — a subset of tenants, or a shard of traffic — is served only by its own infrastructure. One tenant's spike consumes its own cell's capacity, and the majority of customers are unaffected. The cost is real: more nodes than a shared pool needs, cross-cell operations become explicit and awkward, and you must decide what happens when a cell fills up (queue, or route to a spare cell). Cell-based designs are common in systems where a single tenant can be large enough to matter, because otherwise fairness is a scheduling problem you can never fully solve.

Bulkheads give each dependency class its own resource pool. Separate connection pools per downstream service, separate thread pools per workload (interactive versus batch), separate queues per tenant tier. The failure this prevents is subtle: a slow dependency consuming every connection in a shared pool leaves the fast path unable to reach a database that is perfectly healthy.

Circuit breakers stop calling a dependency that is failing, so the caller fails fast instead of accumulating timeouts. Every breaker needs a half-open probe and hysteresis — open at a 50% error rate, close at 5% — or it oscillates and adds load exactly when the dependency is recovering.

Load shedding at the edge is the last resort and the most effective one. Rejecting 10% of requests at the ingress costs almost nothing; letting them all in and timing out costs the capacity needed to serve the other 90%.

## The shared things that quietly re-couple everything

These are the recurring offenders, and each one reintroduces exactly the coupling that the service split removed.

- One shared database. Two "independent" services that write the same tables share a lock, a schema migration, and a failure domain. A migration that blocks a table stops both.
- One shared connection pool. Failover to a second region is theatre if both regions draw from a pool sized for one.
- One credential. A rotated or revoked key, or one leaked key, affects every consumer that holds it. Per-service credentials are also what makes an audit answerable.
- One global rate limiter. The limiter becomes a dependency on the hot path; if it is unreachable or misconfigured, everything is throttled or nothing is.
- One deploy pipeline. A broken pipeline blocks every fix, including the incident fix.

None of these are wrong by default — sharing a database is often the correct trade for a small team. They are wrong when they are unacknowledged, because the design documents then claim an isolation the system does not have.

## Correlated failure is the thing replicas do not fix

Redundancy assumes independence. Failures usually violate that assumption, which is why "we have three copies" so often becomes "we have three copies of the same outage".

The classic sources: a common configuration pushed to every replica (a bad timeout, a wrong TLS flag), the same client library version with the same bug, the same physical rack or availability zone, the same auto-scaling group scaling to zero together, a shared DNS record or load balancer, and a retry storm that arrives at every replica simultaneously.

```text
Bad deploy → all replicas restart together
           → health check fails fleet-wide
           → alerts fire on every instance at once
           → on-call sees 200 alerts and one real cause
```

Two mitigations are cheap and effective. Roll out in waves with a soak between them, so a bad configuration reaches 5% of capacity first. And make the failure domains genuinely independent — different zones, staggered restarts, jittered retries — so a single trigger cannot reach all copies at the same instant.

## Measure it before you need it

Blast radius is testable. Inject the failure in a controlled way and observe what actually breaks: kill one cell, saturate one dependency, revoke a credential in staging. The findings are frequently surprising, because the coupling lives in configuration and shared infrastructure rather than in the call graph. Writing the expected behaviour down before the exercise is what turns it into evidence rather than an anecdote.

## Practice

[Blast Radius](../challenges/principal-engineer-blast-radius) asks you to reason about exactly this: given a failure, which part of the system remains healthy. Make the isolation explicit in the design and show which shared resource would re-couple it.
