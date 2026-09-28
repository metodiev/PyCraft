# Complexity in Practice: Choosing the Right Shape

Big-O describes how cost grows, not how fast code runs. Two implementations can
have the same complexity and differ by an order of magnitude on real inputs, and
the slower algorithm on constants can win until the crossover — but the shape of
your data structure decides the crossover exists at all.

## Growth, not speed

`O(n)` means the work is proportional to input size *up to constants*. Those
constants are not noise: a hash lookup on integers and a hash lookup on objects
with a custom `__hash__` are both `O(1)` and can differ by 100x. What complexity
buys you is a prediction: double the input and the linear scan doubles, while
the hash map barely moves. That prediction is what makes the choice before you
have a profile.

Complexity is also defined per operation, not per program. Appending to a list
is `O(1)`, `x in list` is `O(n)`, and `x in set` is expected `O(1)`. The same
seemingly small change — list to set — moves a nested loop from `O(n^2)` to
`O(n)`.

## Amortised cost

Some operations are occasionally expensive and cheap on average. A CPython list
over-allocates; an append is `O(1)` amortised even though the resize that
happens every so often is `O(n)`. `dict` insertion is `O(1)` amortised, with
rehashing when the table fills. Amortised means you cannot use the worst case
per call to argue the total is bad — but it also means an individual call may
pause, which matters for latency budgets and real-time paths.

## Shape beats micro-optimisation

Consider answering many range sums over a fixed array of `n` values.

| Approach | Build | Query | Total for `q` queries |
| ----- | ----- | ----- | --------------------- |
| Rescan slice per query | `O(1)` | `O(n)` | `O(qn)` |
| Precompute all pairs | `O(n^2)` | `O(1)` | `O(n^2)` |
| Prefix sums | `O(n)` | `O(1)` | `O(n + q)` |

Prefix sums win whenever `q` is large because the expensive work happens once,
and every query is a subtraction of two precomputed values:

```python
def build_prefix(values: list[int]) -> list[int]:
    prefix = [0] * (len(values) + 1)
    for i, value in enumerate(values):
        prefix[i + 1] = prefix[i] + value
    return prefix


def range_sum(prefix: list[int], left: int, right: int) -> int:
    """Sum of values[left:right], half-open."""
    return prefix[right] - prefix[left]
```

The leading zero is what makes the formula uniform: `prefix[i]` is the sum of
the first `i` values, so no boundary case is needed for `left == 0`. Shaving
constant factors off the rescanning version will never close that gap on a
workload with thousands of queries.

The same reasoning applies to counts, `min`/`max` over static data, and
"first index satisfying a predicate" — the general shape is *precompute an index
once, answer in constant or logarithmic time*.

## Time and space

Every precomputation spends memory to save time, and the exchange rate matters.
Prefix sums cost one extra list — negligible. Precomputing all pairs is
`O(n^2)` memory and is prohibitive past a few thousand elements. A hash index
trades a second copy of the keys for near-constant lookup. Make the trade
explicit: state the memory budget, then choose the shape that fits inside it.
A solution that is fast and then dies on the memory limit is not fast.

## Reason about the workload before you write code

Ask two questions first.

**How often does this run?** A slow path invoked once per request has a
different budget from one invoked once per row. If the inner function is called
`q` times per request, its per-call cost is multiplied by `q`; that multiplier
is usually where the choice is decided, not inside the function.

**How does it scale with input?** If the input is fixed at 50 rows, an `O(n^2)`
scan is fine and the simpler code is the better engineering. If the same code
will see 50,000 rows, it is a latent outage. Name the expected size and the
growth rate together; either alone produces the wrong answer.

Finally, choose the shape that keeps the hot path boring. Allocating in a loop,
rebuilding a list per query and rescanning are the mistakes that show up as flat
profiles: no single function is hot because the cost is spread across millions
of small calls. Reduce the count of operations, not the cost of each one.

## Practice

Work through [Range Sum Queries](../challenges/performance-range-sum-queries):
build a prefix-sum index, keep the queries constant-time, and confirm the
trade-off holds when the query count grows far beyond the array size.
