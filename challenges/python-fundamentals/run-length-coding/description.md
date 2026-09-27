# Run-Length Coding

Run-length encoding is the oldest compression trick in the book: replace every
run of repeated characters with the character followed by its length. It is the
format behind bitmap faxes, PCX images and a thousand log-shipping tools — and
it is a perfect exercise in round-tripping data **and** rejecting garbage.

## Your task

Implement two functions that work on strings of ASCII letters only
(`a`–`z` and `A`–`Z`; letters are case-sensitive, so `"aA"` is two runs).

### `encode(text)`

Return the run-length encoded form.

* A run of length `1` is written as just the character — never `"a1"`.
* A run of length `L > 1` is written as the character followed by the decimal
  length, e.g. `"a3"`.
* The empty string encodes to the empty string.
* If `text` contains any character that is not an ASCII letter, raise
  `ValueError`.

### `decode(encoded)`

Return the original text from an encoded string.

* The encoded string must be a sequence of `<letter><digits>` items, where the
  digits are optional but, when present, must be a decimal integer `>= 1`.
  A missing digit group means a run of length `1`.
* Anything else raises `ValueError`: a leading digit, a non-letter, a count of
  `0`, or a trailing bare digit run.

## Examples

| Call | Expected result |
| ---- | --------------- |
| `encode("")` | `""` |
| `encode("abc")` | `"abc"` |
| `encode("aaabbc")` | `"a3b2c"` |
| `encode("aA")` | `"aA"` |
| `encode("a b")` | raises `ValueError` |
| `decode("a3b2c")` | `"aaabbc"` |
| `decode("a12")` | `"a" * 12` |
| `decode("a2b")` | `"aab"` |
| `decode("12a")` | raises `ValueError` |
| `decode("a0")` | raises `ValueError` |
| `decode("a2-")` | raises `ValueError` |

## Constraints

* Standard library only (`re` is allowed).
* `decode` must be a genuine inverse: for every valid encoded string `s`,
  `encode(decode(s)) == s`, and for every letter-only `text`,
  `decode(encode(text)) == text`.
* No printing; return values only.

## Hints

<details>
<summary>Hint 1 — Building runs</summary>

Compare each character with the previous one while you walk the string:

```python
runs = []
for char in text:
    if runs and runs[-1][0] == char:
        runs[-1][1] += 1
    else:
        runs.append([char, 1])
```

Then join, appending the count only when it is greater than `1`.

</details>

<details>
<summary>Hint 2 — Validating before decoding</summary>

Do not silently skip anything you do not understand — that is exactly how a
decoder corrupts data. A single regular expression can validate a whole encoded
string before you expand it:

```python
import re

TOKEN = re.compile(r"([A-Za-z])(\d*)")
# fullmatch the whole string as a sequence of TOKENs, then check
# int(count) >= 1 for every non-empty digit group.
```

`findall` alone is *not* validation: it happily ignores the parts it cannot
match, so `"12a"` would decode instead of raising.

</details>
