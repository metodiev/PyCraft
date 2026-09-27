# Roman Numerals

Two thousand years of bookkeeping, one very strict grammar. Because the Romans
never wrote `IIII` for 4 (they wrote `IV`), a parser that only checks "is this a
valid string of Roman digits" accepts a lot of junk. Implement both directions,
and insist on the canonical form.

## Your task

Implement `to_roman(number)` and `from_roman(text)`.

### `to_roman(number)`

Convert an `int` in the inclusive range `1..3999` into its canonical Roman
numeral, using the subtractive forms:

```
1000 M   900 CM   500 D   400 CD   100 C   90 XC
  50 L    40 XL    10 X     9 IX     5 V    4 IV     1 I
```

* `number` below `1`, above `3999`, or not an `int` at all raises `ValueError`.
* Booleans are not accepted — `True` is not `1` (raise `ValueError`).

### `from_roman(text)`

Convert a **canonical** Roman numeral string back to an `int`.

* Accepts only what `to_roman` would produce. So `"IV"` is `4`, while `"IIII"`,
  `"IIV"`, `"XXXX"`, `"VX"`, `"IC"` and `"MMMM"` all raise `ValueError`.
* `""`, whitespace, and lowercase input raise `ValueError`.
* The result is always `1..3999`.

`from_roman(to_roman(n)) == n` must hold for every valid `n`, and
`to_roman(from_roman(s)) == s` for every value-producing `s`.

## Examples

| Call | Expected result |
| ---- | --------------- |
| `to_roman(1)` | `"I"` |
| `to_roman(4)` | `"IV"` |
| `to_roman(9)` | `"IX"` |
| `to_roman(40)` | `"XL"` |
| `to_roman(944)` | `"CMXLIV"` |
| `to_roman(3999)` | `"MMMCMXCIX"` |
| `from_roman("MCMXCIV")` | `1994` |
| `from_roman("IIII")` | raises `ValueError` |
| `from_roman("iv")` | raises `ValueError` |
| `to_roman(0)` | raises `ValueError` |

## Constraints

* Standard library only.
* `to_roman` returns a `str` in uppercase.
* `from_roman` accepts only the canonical spelling described above — no
  "lenient" parsing, no normalising, no uppercase-conversion of the input.

## Hints

<details>
<summary>Hint 1 — Greedy subtraction for encoding</summary>

Walk the value down through a descending table that includes the subtractive
pairs, appending as you go:

```python
TABLE = [(1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), ...]
for value, symbol in TABLE:
    while number >= value:
        result += symbol
        number -= value
```

</details>

<details>
<summary>Hint 2 — Validating the decode without a giant regex</summary>

The cleanest check is a round trip: decode with a simple left-to-right scan, then
re-encode and compare.

```python
def _decode(text):
    values = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}
    total = 0
    for index, char in enumerate(text):
        value = values[char]
        # a smaller numeral before a larger one is subtractive
        if index + 1 < len(text) and value < values[text[index + 1]]:
            value = -value
        total += value
    return total
```

Then `from_roman` returns `_decode(text)` only if `to_roman(_decode(text)) == text`
— that single comparison rejects `IIII`, `MMMM`, `VX` and every other
non-canonical spelling at once.
</details>
