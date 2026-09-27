# FizzBuzz

The interview classic. Build the sequence of the numbers `1..n`, but replace the
numbers that are divisible by 3 and/or 5.

## Your task

Complete the function `fizzbuzz(n)` so it **returns a list of strings** with one
element per integer from `1` to `n`, in order, using these rules:

| Condition on the number | Element |
| ----------------------- | ------- |
| divisible by both 3 and 5 | `"FizzBuzz"` |
| divisible by 3 | `"Fizz"` |
| divisible by 5 | `"Buzz"` |
| none of the above | the number as a string |

If `n` is `0` or negative, return an empty list.

## Examples

| Call | Expected result |
| ---- | --------------- |
| `fizzbuzz(0)` | `[]` |
| `fizzbuzz(1)` | `["1"]` |
| `fizzbuzz(3)` | `["1", "2", "Fizz"]` |
| `fizzbuzz(5)` | `["1", "2", "Fizz", "4", "Buzz"]` |
| `fizzbuzz(15)[-1]` | `"FizzBuzz"` |

## Constraints

* `n` is an `int` (it may be zero or negative).
* Return a `list[str]` — every element is a string, including plain numbers
  (`"7"`, not `7`).
* The list has length `n` whenever `n > 0`.

## Hints

<details>
<summary>Hint 1 — Check "both" first</summary>

`15` is divisible by 3 *and* by 5. If you test `n % 3 == 0` before
`n % 15 == 0`, `15` becomes `"Fizz"` and your output is wrong. Put the most
specific condition first:

```python
if value % 15 == 0:
    result.append("FizzBuzz")
elif value % 3 == 0:
    ...
```
</details>

<details>
<summary>Hint 2 — Looping from 1 to n inclusive</summary>

`range(1, n + 1)` stops at `n` because the stop value is *excluded*. For
`n <= 0` the same expression already produces an empty range, so the natural
loop yields `[]` for free.
</details>
