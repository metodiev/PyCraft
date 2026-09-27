# Capacity & Cost Planner

This is the decision a staff or principal engineer actually owns: **how much
infrastructure to buy, and what it costs to stay up.**

You are given a traffic forecast, a catalogue of instance types and a
reliability target. Produce a fleet that serves the peak within the SLO, survives
the loss of one failure domain, and costs as little as possible.

## Your task

Implement four functions in `solution.py`.

### `instance_capacity(instance, utilisation)`

The sustained concurrency one instance serves, as a **floor**:

```
floor(instance.vcpu * utilisation)
```

`utilisation` is a decimal fraction (0.6 = 60%). It must be greater than 0 and
at most 1.

### `peak_concurrency(forecast, safety_factor)`

The load the fleet must survive. The forecast is a list of hourly concurrency
readings; the peak is the maximum, multiplied by the safety factor and rounded
**up** (a fleet cannot be half an instance):

```
ceil(max(forecast) * safety_factor)
```

Reject an empty forecast. A peak of 0 needs no instances.

### `plan_fleet(forecast, instances, *, utilisation, safety_factor, failure_domains)`

Choose a fleet.

- Pick the **cheapest instance type** by price per unit of capacity, i.e. the
  lowest `price_per_hour / instance_capacity(...)`. Break ties by the instance
  name, ascending, so the result is deterministic.
- `count` is the number of instances **per failure domain**, sized so the fleet
  still meets the peak after `failure_domains - 1` of them are lost. Because
  every instance is the same type, the surviving capacity is
  `count * (failure_domains - 1) * instance_capacity`, which must be `>= peak`.
  Solve for the smallest such `count`:

  ```
  count = ceil(peak / (instance_capacity * (failure_domains - 1)))
  ```

  So `count` is derived from the *survivors*, not from the total. Sizing for the
  total and then dividing is the mistake this challenge exists to catch: with
  three domains and a peak of 300, a per-domain count of 100 gives 300
  instances but only 200 surviving capacity.
- Return a `Fleet` with the chosen `instance`, `count` (per domain),
  `total_instances` (`count * failure_domains`), `capacity` (total sustained
  concurrency, i.e. `total_instances * instance_capacity`), and `hourly_cost`
  (`total_instances * price_per_hour`).

An instance that offers **no** usable capacity (a zero-capacity result) can
never be chosen, at any price. If **no** offered type offers usable capacity,
raise `InsufficientCapacityError` — that is the only genuine dead end, because a
type with positive capacity can always reach any peak by adding instances.

### `months_to_break_even(monthly_cost, upfront_cost)`

The payback period in months, rounded **up**, for a commitment that costs
`upfront_cost` and saves `monthly_cost` per month. A non-positive saving never
pays back — raise `ValueError`.

## Examples

```pycon
>>> small = Instance("small", vcpu=2, price_per_hour=0.10)
>>> instance_capacity(small, 0.5)
1
>>> peak_concurrency([100, 250, 180], 1.2)
300
>>> plan_fleet(
...     [100, 250, 180], [small], utilisation=0.5, safety_factor=1.2, failure_domains=3
... )
Fleet(instance='small', count=150, total_instances=450, capacity=450, hourly_cost=45.0)
```

150 per domain leaves 300 surviving across the remaining two domains, exactly
the peak. 100 per domain would leave only 200 and is wrong.

## Constraints

- Standard library only.
- No floating-point drift in the capacity arithmetic: compute with integers
  where you can, and use `math.ceil` deliberately.
- `plan_fleet` must be deterministic — two calls with the same input give the
  same fleet.
- Instances are immutable; do not mutate the input list.

## Hints

<details>
<summary>Hint 1 — Why per-domain, not total</summary>

If you size for the peak in total and then spread it across domains, losing one
domain takes the fleet under the peak. Size each domain so the *survivors*
cover the peak: `per_domain * (failure_domains - 1) >= peak`.

</details>

<details>
<summary>Hint 2 — Cheapest per unit, not cheapest</summary>

A \$0.10 instance that serves 1 unit costs \$0.10 per unit; a \$0.30 instance
that serves 4 costs \$0.075. The second is cheaper to run. Compare
`price / capacity`, and guard against division by zero for an instance that
serves nothing.

</details>

<details>
<summary>Hint 3 — Round the peak, then the fleet</summary>

`ceil` the peak first, then divide by per-instance capacity and `ceil` again.
Ceiling twice is not the same as ceiling once at the end, and the difference is
exactly the instance you would have been short of.

</details>

<details>
<summary>Hint 4 — Break-even rounding</summary>

A payback of 3.1 months takes 4 months to actually pay back. Use `ceil`, and
reject a non-positive saving rather than returning infinity.
</details>
