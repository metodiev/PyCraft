# Capacity Planning: From QPS to Machines

Capacity estimates fail in two ways: they are wrong, or they are unfalsifiable. A useful plan is explicit about being wrong by stating the assumptions that would change it, and precise enough that a reviewer can pull a specific lever instead of saying "this feels optimistic".

## Start from the number you can defend

Work outward from the two figures a product owner can argue with: how many people you serve, and what one of them does per day.

```text
1,000,000 daily active users
        60 requests per active user per day
= 60,000,000 requests per day
÷        86,400 seconds per day
=           694 requests per second, average
```

Every term is a decision. Is an "active user" someone who opens the app, or someone who logs in? Does the mobile client batch five user actions into one request? Write the answers next to the numbers, because the average QPS figure is only useful as an input to the next step.

## Peak is what you provision

Traffic has a shape: a morning ramp, a lunchtime plateau, an evening peak, a quieter weekend. The peak-to-average factor follows from the product — a workplace tool concentrates load into working hours, a consumer app spreads it across the day. For something with a strong daily rhythm, a peak of six times the daily average is a defensible opening bid.

```text
694 QPS average × 6 = 4,164 QPS
```

Round up to 4,200 and state the assumption set in one sentence: 1M daily actives, 60 requests each, a 6× peak factor. "Peak QPS is 4,200" is an assertion nobody can challenge. "Peak QPS is 4,200 given 60M requests a day and a 6× peak factor" is an argument someone can win — and if they win it, the fleet size changes by a third, which is the whole point of writing it down.

Autoscaling covers the rest of the curve, but only if it finishes in time. Scaling out takes minutes; the capacity that absorbs the morning ramp has to be running before the ramp starts.

## Utilisation is the variable that bites

You cannot run servers near saturation and still deliver the latency you promised. In the simplest queueing model — random arrivals to a single server, the M/M/1 case — mean response time grows as 1/(1 − utilisation), measured in service times. Real systems with many workers are less dramatic, but they keep the same shape:

| Target utilisation | Mean response time |
| --- | --- |
| 50% | 2× |
| 80% | 5× |
| 90% | 10% |
| 95% | 20× |
| 99% | 100× |

Read the table as total time, service included: at 50% utilisation a request spends about one service time waiting, at 90% it spends nine. The curve looks flat until roughly 70% and then turns vertical, so "we have 10% spare capacity" means something very different at 60% utilisation and at 89%.

Choose a target — 60% at peak is a common default for latency-sensitive services — and treat the rest as the buffer that absorbs retries, a slow dependency and the gap between your peak model and reality. A service planned to 95% has no room for any of those, which is why it is the one that pages at 3 a.m.

## Little's law as a cross-check

Little's law relates the three quantities people quote separately: concurrency, throughput and latency.

```text
concurrency = throughput × latency
```

At 4,200 QPS and 25 ms mean latency, 105 requests are in flight at any instant. That is a design constraint, not trivia: 105 in-flight requests sharing a pool of 50 database connections is impossible, and the pool — not the CPU — then caps throughput at 50 ÷ 0.025 = 2,000 QPS. Concurrency limits are the real capacity of most systems, and they are usually set by accident.

Run the arithmetic in both directions. With 200 connections and the same 25 ms latency, the ceiling is 8,000 QPS. Treat that as an upper bound rather than a forecast: it holds only if the boxes have the CPU to serve 8,000 requests a second, and a saturation test is what tells you whether they do. The value of the sum is that it puts a number on which limit binds first.

## From QPS to machines

Measure per-instance throughput under realistic load instead of trusting a benchmark. Say one instance serves 200 QPS while holding your latency target, and you plan to use 60% of that — 120 QPS per instance — so that queueing stays on the flat part of the curve.

```text
Peak 4,200 QPS; one instance sustains 200 QPS
Target 60% utilisation → 120 usable QPS per instance

Steady state:  4,200 ÷ 120            = 35 instances
Zone loss:     4,200 ÷ 120 ÷ (2/3)    = 52.5 → 53 instances
Plus one for rolling replacement       = 54 instances
```

The last two lines are the survivability constraint. With three zones and one lost, two thirds of the fleet has to deliver the same 4,200 QPS, so the fleet must be 1.5× the steady-state requirement. The extra instance covers one node out for maintenance or a rolling deploy. Both constraints apply, and the fleet is the larger of the two answers — here, zone tolerance dominates by a wide margin.

That is why 54 instances sit at roughly 39% utilisation on a normal day, not 60%: the target applies to the degraded state, and the surplus is the price of meeting it. Buying that deliberately is capacity planning; discovering it during an incident is not.

## Practice

Work the same estimate for a different product in [Capacity & Cost Planner](../challenges/principal-engineer-capacity-cost-planner), which asks for a fleet that meets an SLO at the lowest cost while surviving a failure domain. State your peak factor and utilisation target as numbers — they are the two assumptions most likely to be wrong, and the two most worth defending.
