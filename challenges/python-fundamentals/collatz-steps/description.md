# Collatz Steps

Pick a positive integer. If it is even, halve it; if it is odd, multiply by 3
and add 1. Repeat until you reach `1`. Nobody knows whether every start
eventually arrives, but for the numbers you will be given it always does — and
the number of steps varies wildly (`7` takes 16 steps, `27` takes 111).

## Your task

Implement two functions.

### `collatz_steps(n)`

Return the number of steps needed to reach `1`, starting from `n`.

* `collatz_steps(1)` is `0` — you are already there.
* `n` must be an integer `>= 1`; anything smaller raises `ValueError`.

### `longest_chain(limit)`

Return the starting value in `1..limit` (inclusive) that takes the **most**
steps. When several starting values tie, return the **smallest** one.

* `limit` must be an integer `>= 1`; anything smaller raises `ValueError`.

## Examples

| Call | Expected result | Why |
| ---- | --------------- | --- |
| `collatz_steps(1)` | `0` | already 1 |
| `collatz_steps(2)` | `1` | `2 → 1` |
| `collatz_steps(6)` | `8` | `6 → 3 → 10 → 5 → 16 → 8 → 4 → 2 → 1` |
| `collatz_steps(27)` | `111` | the famous long chain |
| `longest_chain(1)` | `1` | only candidate |
| `longest_chain(6)` | `6` | step counts `0,1,7,2,5,8` |
| `longest_chain(10)` | `9` | 19 steps, more than `6`'s 8 |
| `longest_chain(19)` | `18` | `18` and `19` both take 20 steps — smallest wins |

## Constraints

* Standard library only.
* `collatz_steps(0)`, `collatz_steps(-3)`, `longest_chain(0)` and
  `longest_chain(-1)` must raise `ValueError`.
* `longest_chain(limit)` may be called with `limit` up to a few thousand, so
  keep the loop cheap — recomputing the chain of every start from scratch is
  fine, but caching results you already know is better.

## Hints

<details>
<summary>Hint 1 — The step loop</summary>

A `while` loop with the two rules and a counter:

```python
steps = 0
while n != 1:
    n = n // 2 if n % 2 == 0 else 3 * n + 1
    steps += 1
```

Use `//` (integer division), not `/`, so `n` stays an `int`.

</details>

<details>
<summary>Hint 2 — Ties and the smallest start</summary>

Track the best start and the best step count separately, and only replace the
best when you find a **strictly** better count. Scanning `1..limit` upwards
then keeps the smallest start automatically:

```python
best_start, best_steps = 1, 0
for start in range(2, limit + 1):
    steps = collatz_steps(start)
    if steps > best_steps:      # strict: keeps the first (smallest) on a tie
        best_start, best_steps = start, steps
```

</details>
