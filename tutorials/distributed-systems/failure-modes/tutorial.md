# Failure Modes: Timeouts, Retries and Partial Failure

Distributed failures do not look like local ones. A function either returns or raises; a remote call has a third outcome — no answer — and that one is where systems hang. Everything here follows from taking that outcome seriously.

## The missing outcome, and the timeout that supplies it

A remote call has three outcomes: success, failure, and no answer. The third arrives when the peer is unreachable, when the response is lost, or when the peer is alive but too slow to reply within any meaningful horizon. TCP will not rescue you: with a peer that accepts connections and then never responds, the connection stays open indefinitely. Without an explicit deadline, the call inherits an unbounded one, a worker thread parks on a socket, and a bounded thread pool fills until the process stops serving anyone — typically while every health check still reports green.

So every remote call gets an explicit timeout covering connection establishment, request write and full response read, and the effective timeout is the smallest one in the chain:

```python
import requests

response = requests.get(
    url,
    timeout=(0.5, 2.0),   # (connect, read) — both required
    headers={"Accept": "application/json"},
)
```

Two rules make deadlines behave. First, propagate a *deadline* rather than a duration. If a request has 800 ms left, the downstream call gets 800 ms minus a small budget for processing the response — passing "5 seconds" at every layer means the total is unbounded and the top-level deadline is decorative. Second, treat a timeout as neither success nor in-flight: the request may well have been executed by the peer, which is exactly why write paths need idempotency keys rather than naive retries.

A timeout that is too generous is a silent failure mode. If the caller gives up at 30 s while the peer's own budget is 5 s, the caller mostly waits for nothing. Measure the dependency's latency distribution and set the timeout near the tail you are willing to pay, not an order of magnitude above it.

## Retries cost capacity, so budget them

A retry is not free: it consumes a connection, a thread, and a share of the failing dependency's remaining capacity. When a dependency is partially failing, retries multiply the load on it:

- One call with 3 retries against a dependency already at 100 % utilisation triples the offered load at the moment it can least absorb it.
- Retries that fire at the same instant, or after a fixed delay, synchronise: they arrive together, overwhelm the recovering dependency, and restart the outage. The signature is obvious — traffic falls, spikes above steady state, falls again.
- Retrying a non-retryable error wastes the budget a genuinely transient error needed. Validation and authentication errors mean the request is wrong and will fail identically forever.

Practical limits:

- Cap total attempts (2–3 for an interactive path) and cap *time* from the same deadline as the original request.
- Retry only idempotent operations, or supply an idempotency key so a duplicate cannot double-apply an effect.
- Use a token budget per call site: once it is spent, fail fast rather than letting every in-flight request spawn retries.
- Classify retryable errors from the dependency's own semantics, not by "everything except 2xx".

## Exponential backoff with jitter

Backoff spreads retries over time; jitter stops them from synchronising. The full-jitter form is the simplest that works well:

```python
import random
import time

def backoff_delay(attempt, base=0.1, cap=5.0):
    ceiling = min(cap, base * (2 ** attempt))
    return random.uniform(0, ceiling)   # full jitter
```

Without jitter, clients that failed at the same moment wait the same interval and retry at the same moment, so the dependency sees a wave rather than a trickle and the storm repeats. With full jitter the expected delay still grows exponentially, but arrivals spread.

Two refinements: apply a deadline to the whole retry sequence so it cannot exceed the caller's budget, and let the server steer the schedule. A `Retry-After` header, or a delay in an error body, communicates when the server expects to be ready better than any client-side guess. Pacing clients slightly under the server's stated capacity with a token bucket is the same idea applied to throughput.

## Circuit breakers: fail fast when the dependency is clearly down

Timeouts bound one attempt; a circuit breaker bounds *repeated* attempts against a dependency that is clearly not recovering. It is a state machine:

- **Closed**: calls pass through. Consecutive failures (or a failure-ratio window) trip it.
- **Open**: calls fail immediately with a local error and spend no time or capacity on the network. A timer starts.
- **Half-open**: after the timer, a limited number of trial calls are allowed. Success closes the circuit; failure re-opens it, usually with a longer interval.

What the breaker must not do: count a permanent error (a 400 caused by a malformed request) toward the failure threshold, since that is a local bug, not an outage — a run of them would open the circuit and make a working dependency unreachable, which the fanout project's rubric calls out explicitly. Nor should it retry a refused call; the point of open is to spend nothing. Half-open probes must be a trickle, not a flood, or the recovering dependency is knocked over by the probes.

## Degrade a feature, not the request path

The design goal is that one slow dependency affects one feature. That requires isolation decisions *before* the incident:

- Separate thread pools or connection pools per dependency, so a stalled dependency cannot consume every worker in the process and starve unrelated calls. A single shared pool makes any one dependency a global blocker.
- Give every dependency its own timeout, breaker, and fallback: cached or default responses, or omitting that section of the page.
- Set a total budget for the request. When it is exhausted, return partial results with an honest indicator rather than waiting for the slowest dependency — a page that renders without recommendations beats a blank error.
- Make the degraded state visible and distinguishable from success in metrics and logs. A fallback that is reported as success means you find out about the outage from a customer, long after the fallback has become the normal path.

## Practice

[Distributed Notification Fanout](../challenges/distributed-systems-notification-fanout) applies all three ideas in one place: per-channel rate limiting, retry classification that distinguishes transient from permanent failures, a circuit breaker driven by an injected clock, and a report that must not claim success for work that was left unfinished.
