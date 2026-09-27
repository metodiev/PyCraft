# Canary Rollout with Error Budgets

A release is a sequence of decisions, not a button. This challenge models the
loop a principal engineer is accountable for: **shift a little traffic, look at
the error budget, and either go further or stop.**

Implement a rollout state machine in `solution.py`.

## Your task

### `error_rate(observations)`

The fraction of requests that failed, over a list of `(total, failed)` pairs:

```
sum(failed) / sum(total)
```

An empty list, or a total of zero, is `0.0`. A pair with negative counts, or
with `failed > total`, raises `ValueError` — telemetry that cannot be true must
not be silently averaged away.

### `budget_burned(observations, slo)`

How much of the error budget is consumed, as a fraction.

`observations` are the *baseline* (total requests and failures for the whole
service); `slo` is the target success fraction (0.999 = 99.9%).

- The budget is the allowed failures: `(1 - slo) * total`.
- Burned is `failed / budget`, so `1.0` means the budget is exactly exhausted.
- If `slo` is 1.0 the budget is zero: any failure is infinite burn and must
  raise `ValueError`, rather than dividing by zero.

### `decide(stage, observations, *, slo, max_burn, threshold)`

The decision for one rollout step.

Given the `stage` (a promoted fraction, e.g. 0.05) and its `observations`:

- Compute the **canary** error rate from `observations.canary` and the
  **baseline** error rate from `observations.baseline`.
- **`HALT`** if the canary's error rate is **strictly greater** than `threshold` —
  an absolute ceiling, independent of the baseline.
- Otherwise **`ROLLBACK`** if the canary's error rate is **strictly greater**
  than `baseline_rate * (1 + max_burn)` — a *relative* regression against what
  the service already does. Express it as this multiplication rather than
  subtracting and dividing, so a baseline of `0` needs no special case (any
  failure exceeds it) and the boundary does not drift in floating point.
- Otherwise **`PROMOTE`**.

Both comparisons are strict, so a canary exactly at the ceiling, or exactly at
the tolerance, promotes.

Order matters: the absolute ceiling is checked first, so a canary that is
already broken halts rather than being compared against an equally broken
baseline.

### `run_rollout(stages, observations, *, slo, max_burn, threshold)`

Drive the whole sequence.

- Walk `stages` in order, deciding each from its observations.
- Stop at the first decision that is not `PROMOTE`.
- Return a `Rollout` recording the final `stage` reached, the `decision`, the
  `canary_error_rate` and `baseline_error_rate` of that step, and the number of
  `steps_taken`.

`observations` is a list of `Observation(canary, baseline)`, one per stage, each
entry a list of `(total, failed)` pairs. A length mismatch between `stages` and
`observations` raises `ValueError`.

## Examples

```pycon
>>> error_rate([(1000, 10)])
0.01
>>> decide(
...     0.05,
...     Observation(canary=[(1000, 10)], baseline=[(1000, 2)]),
...     slo=0.999, max_burn=0.5, threshold=0.05,
... )
Decision.PROMOTE
>>> decide(
...     0.05,
...     Observation(canary=[(1000, 90)], baseline=[(1000, 2)]),
...     slo=0.999, max_burn=0.5, threshold=0.05,
... )
Decision.HALT
```

## Constraints

- Standard library only.
- No wall-clock or randomness: every decision is a pure function of its input.
- `ROLLBACK` and `HALT` keep the observed rates on the returned `Rollout`, so
  the evidence survives the incident.
- Do not mutate the inputs.

## Hints

<details>
<summary>Hint 1 — Why the ceiling is checked first</summary>

If the service is already at 8% errors and the canary is at 9%, the *relative*
regression is small, but shipping a 9% error rate is not acceptable. The
absolute threshold exists to catch that case, so it must be evaluated before the
relative comparison.

</details>

<details>
<summary>Hint 2 — Burn is a fraction of a budget</summary>

At 99.9% SLO, 1000 requests permit exactly one failure. Two failures is a burn of
2.0 — you have spent twice the budget. Reporting it as a *fraction* rather than
a percentage keeps the numbers comparable across SLOs.

</details>

<details>
<summary>Hint 3 — Stopping means stopping</summary>

The rollout must not keep evaluating stages after a non-`PROMOTE`. The recorded
`steps_taken` counts the steps actually decided, including the failing one.
</details>
