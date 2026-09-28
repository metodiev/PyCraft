# Cost as an Engineering Constraint

Cost is a design property, like latency or availability. Treated as a bill that arrives at the end of the month and is investigated afterwards, it can only be explained. Treated as an input to the design, it changes the shape of the system while the shape is still cheap to change.

## Where the money actually goes

Bills are rarely proportional to request count. A small share of the workload produces most of the spend, and the reasons are consistent across systems:

- Hot paths with expensive per-request work: a full-text query, an image transform, an unindexed scan. A 2% slice of traffic can be 40% of compute.
- Time-and-capacity charges. An idle database instance, a provisioned cluster, a NAT gateway, a reserved IP: these accrue while doing nothing. Idle cost is the easiest to overlook because no alert fires for a resource that is merely present.
- Egress. Data leaving the network boundary is charged per gigabyte and is often invisible in development, because everything is local.
- Storage that is written once and never read: logs nobody queries, debug artefacts, snapshots of snapshots.

The first exercise is not optimisation; it is attribution. Break the bill down by workload or team until someone can point at a number and say "that is the semantic search backfill". Cost you cannot attribute is cost you cannot reduce.

## Levers, and what each costs

**Rightsizing** is usually the largest immediate win. Instances are commonly provisioned for a peak that never arrives, and a fleet at 15% average CPU is paying for headroom nobody uses. Resizing down trades safety margin for money; check the memory and connection ceilings before assuming a smaller instance is safe, since those — not CPU — are what most services actually saturate. Choose the target utilisation deliberately, and remember the queueing curve: 90% utilisation is not "safe headroom", it is a latency cliff.

**Autoscaling** converts a fixed charge into a variable one, at the cost of a floor. It is a poor fit for spiky traffic if scaling takes minutes, because you either run a large floor or serve the spike slowly. It also interacts with shutdown: a batch job killed by a scale-in is a bug that surfaces months later.

**Reserved or committed capacity** cuts the unit price in exchange for a commitment. It is correct for a stable baseline and wrong for a workload you are about to move.

**Retention and lifecycle policies** are the cheapest large win in most systems, because the data you delete costs nothing to store and nothing to scan. A lifecycle rule that moves objects to cold storage after 30 days and deletes them after 180 is a configuration change with a permanent effect. Do establish what you are legally required to keep before deleting anything, and keep the policy visible in code rather than in a console checkbox — an undocumented retention change is a compliance incident waiting to happen.

## The unit-cost framing

Absolute spend says nothing about whether the system is improving: growth in traffic makes any absolute number rise. The measurable quantity is cost per unit of delivered work.

```text
Before: $12,161/month ÷  900M requests = $0.0000135 per request
After:  $14,300/month ÷ 1,800M requests = $0.0000079 per request
```

Spend rose by 18% while unit cost fell by 41%. Both statements are true, and only the second supports a claim that the engineering improved — the fleet did not double because the fixed capacity absorbed the extra traffic, which is exactly the effect a per-request number shows and a total never does. Define the unit that matches the product — cost per request, per active tenant, per minute processed — and track it over time.

A falling unit cost can also hide a problem: total spend can grow faster than revenue even while cost per request falls, if the workload mix shifts toward expensive requests. Track both, and use the unit cost to evaluate engineering work rather than to justify the bill.

## Cost at design time

The decisions that determine 80% of a system's steady-state bill are made before launch: which data store, how many copies, which regions, what is cached, and what retention looks like. A cost model is worth building alongside the capacity model, because the two share inputs.

```text
Peak 4,200 QPS, average 694 QPS → 1.8B requests/month
Compute: 54-instance fleet, zone-tolerant, 60% target utilisation
         54 × $0.21/hour × 730 hours  = $8,278
Storage: 12 TiB × $0.023/GiB          =   $283
Egress:  40 TB  × $0.09/GB            = $3,600
Total                                 = $12,161
Unit cost: $12,161 ÷ 1.8B             = $0.0000068 per request
```

Two things this model forces into the open. First, egress is 30% of the total, so a design that returns slightly smaller payloads moves the bill more than a round of instance tuning. Second, look at what the last line does not include: the fleet is 54 instances because of the zone-loss requirement, not because of average load, and the compute line carries that decision every hour of every month. Headroom is a design choice with a price, and the price belongs in the model.

Cost models go stale; the traffic mix changes and prices change. Treat them like any other capacity estimate — state the assumptions, and revisit when the assumptions move.

## Practice

[Capacity & Cost Planner](../challenges/principal-engineer-capacity-cost-planner) makes the trade explicit: build a fleet that meets an SLO while surviving a failure domain, at the lowest cost. Note how much of the final number comes from headroom and duplication decisions rather than from instance selection.
