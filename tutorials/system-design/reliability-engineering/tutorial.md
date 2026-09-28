# Reliability: SLOs, Error Budgets and Degradation

Reliability work goes wrong when it is framed as an ambition rather than a number. "Highly available" cannot be argued with, funded, or exceeded; "99.9% of requests under 300 ms over 30 days" can be all three. This tutorial is about the arithmetic that turns reliability into something a team can spend.

## SLI, SLO, SLA

The three terms are stacked, and conflating them causes most of the confusion.

- An **SLI** is what you measure: the proportion of requests that completed successfully, the proportion under a latency threshold, or the freshness of a dataset. It must be something a script can compute from real telemetry.
- An **SLO** is the target for that measurement: 99.9% of requests over a rolling 30-day window.
- An **SLA** is a contract with a consequence attached — a credit, a refund, a penalty. SLAs belong to lawyers and finance; SLOs belong to engineers, and they should be stricter, because the contract is the floor you never want to reach.

Pick a handful of SLIs that map to user experience, not to components. "API gateway CPU" is not an SLI. "Search returns results in under 400 ms for 99% of queries" is.

## The error budget is the useful part

An SLO of 99.9% over a 30-day month means you are allowed to be unavailable for 0.1% of the time.

```text
30 days × 24 h × 60 min = 43,200 minutes
43,200 × 0.001          = 43.2 minutes per month
```

Forty-three minutes. That number is not a target to consume; it is a budget you may spend, and different design choices have different prices. Two minutes of a bad deploy and five minutes of a DNS change burn seven of the forty-three — about 16% of the month. Tighten to 99.99% and the allowance drops to 4.32 minutes — a single slow rollback exceeds it.

Request-based budgets are often sharper: 60 million requests a month at 99.9% permits 60,000 failures. At 3,000 failed requests a minute — a modest partial outage — that allowance is gone in twenty minutes. The budget makes the cost of an incident legible in the same unit as the cost of a feature.

This is what converts reliability from an argument into a negotiation. When the budget is exhausted, the trade is mechanical: freeze risky changes and spend the next sprint on hardening. When the budget is healthy, the team can ship aggressively with the reverse argument. Nobody has to win a debate about whether reliability matters.

## Alert on burn rate, not on a threshold

A single threshold — "page when error rate exceeds 1% for five minutes" — is either too noisy or too slow, because it says nothing about how fast the budget is disappearing. Burn rate fixes that: a burn rate of 1 consumes the budget in exactly the 30-day window, so a burn rate of 14.4 exhausts it in about two days.

```text
30 days ÷ 14.4 ≈ 2.1 days
one hour in a 30-day month = 1/720 of it, so 14.4× for one hour ≈ 2%
```

Pair a fast signal with a slow one. Page when the one-hour window is above 14.4× *and* the five-minute window is too, so the alert fires quickly but also clears quickly instead of staying on after the incident ends. File a ticket when six hours sit above 3×. The fast alert catches outages; the slow one catches a steady leak that a single threshold would never notice.

## Degradation: shedding work instead of failing

Graceful degradation means giving up part of the product so the core path survives. When a dependency is slow, the alternatives are to wait (and burn concurrency), to fail (and burn the budget), or to serve a smaller answer.

Useful patterns, roughly in order of how much they cost you:

1. Skip optional work. Recommendations, avatars, personalisation and view counts are candidates; authentication and payment are not.
2. Serve stale data from cache with an explicit age, rather than blocking on the origin.
3. Open a circuit breaker per dependency so failures are answered immediately instead of consuming threads.
4. Shed load at the edge. Rejecting a request before doing work is far cheaper than timing out after it.
5. Fail reads before writes if the write path is what is saturating the system.

Two traps. First, retries amplify load — three retries per layer multiplies a dependency's traffic, so retries need a budget and jittered backoff. Second, degraded mode is itself a feature on the critical path: it needs its own SLI, a test that exercises it, and hysteresis (enter degraded mode at a higher error rate than the one you leave it at) so the system does not oscillate between modes.

## Practice

[Canary Rollout](../challenges/principal-engineer-canary-rollout) gives you a change to release against a measurable error budget. Decide your SLO, compute the minutes it allows, and set the rollback rule from the budget rather than from intuition.
