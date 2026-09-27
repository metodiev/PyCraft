# Range Sum Queries

Answer many range-sum queries over a static list, fast enough that a naive
scan per query is too slow.

## Your task

Implement `solution.py` so that:

- `build_prefix_sums(values)` returns a prefix-sum list where `result[i]` is the
  sum of `values[:i]`, so `result[0] == 0` and `len(result) == len(values) + 1`.
- `range_sum(prefix, start, end)` returns the sum of `values[start:end]`.

Each query must be answered in constant time. Recomputing the sum inside
`range_sum` passes the visible tests and fails the hidden ones.

## Examples

| Call | Result |
| --- | --- |
| `build_prefix_sums([1, 2, 3])` | `[0, 1, 3, 6]` |
| `range_sum(build_prefix_sums([1, 2, 3]), 1, 3)` | `5` |

## Constraints

- Standard library only.
- `range_sum` must not iterate over the range.

## Hints

<details>
<summary>Hint 1 - Why a leading zero</summary>

Starting with 0 means `range_sum(0, k)` needs no special case.

</details>

<details>
<summary>Hint 2 - The O(1) identity</summary>

`sum(values[start:end])` equals `prefix[end] - prefix[start]`.

</details>
