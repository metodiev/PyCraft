# Word Count

Every log pipeline, search indexer, and linter starts with a word counter. The
interesting part is deciding exactly what a "word" is.

## Your task

Complete the function `word_count(text)` so it returns a dict mapping each
**word** to the number of times it occurs.

Rules:

1. A word is a maximal run of **ASCII letters and digits** (`a-z`, `A-Z`,
   `0-9`). Characters such as `_`, `-`, `'`, `.`, whitespace and any non-ASCII
   letter (e.g. `é`, `ß`, `中`) are **not** part of a word.
2. A word ends when a non-word character is met, so `"well-known"` produces
   `"well"` and `"known"`, and `"don't"` produces `"don"` and `"t"`.
3. Comparison is **case-insensitive**: fold to lowercase before counting, so
   `"The the THE"` is `{"the": 3}`.
4. The returned dict contains only words that actually occur — no zero counts.

Empty input, or input with no alphanumeric run at all, yields `{}`.

## Examples

| Call | Expected result |
| ---- | --------------- |
| `word_count("")` | `{}` |
| `word_count("hello world")` | `{"hello": 1, "world": 1}` |
| `word_count("The the THE")` | `{"the": 3}` |
| `word_count("one, two; one!")` | `{"one": 2, "two": 1}` |
| `word_count("well-known")` | `{"well": 1, "known": 1}` |
| `word_count("café")` | `{"caf": 1}` |

## Constraints

* `text` is a `str`; it may be empty and may contain Python/Unicode characters.
* Return `dict[str, int]`. Dict ordering is not checked, but every count must be
  at least `1`.

## Hints

<details>
<summary>Hint 1 — Splitting on "not a word character"</summary>

A run of letters/digits can be extracted with the `re` module:

```python
import re

re.findall(r"[a-zA-Z0-9]+", text)
```

Note that `\w` in Python's `re` matches Unicode letters such as `é`, so it is
*not* what this challenge asks for.
</details>

<details>
<summary>Hint 2 — Counting without a library</summary>

`collections.Counter` is stdlib (allowed), but `collections.defaultdict(int)`
or a plain `dict.get(word, 0) + 1` is just as good. Either way, lowercase each
token before you count it.
</details>
