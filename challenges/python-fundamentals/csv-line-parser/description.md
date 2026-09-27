# CSV Line Parser

Every data pipeline eventually meets an export that "is basically CSV". Half of
them quote fields with commas inside, and a parser that splits on `,` corrupts
the data silently — the worst possible failure. Parse it properly, and reject
what you cannot understand.

## Your task

Complete the function `parse_csv_line(line)` so it returns the list of fields of
a single CSV record. Parse the string yourself with the rules below; the `csv`
module resolves several of these ambiguities differently, so do not delegate to
it.

### Fields

| Situation | Result |
| --------- | ------ |
| Fields are separated by `,` | `"a,b"` → `["a", "b"]` |
| An empty line is one empty field | `""` → `[""]` |
| A field whose **first** character is `"` is quoted | `'"a,b"'` → `["a,b"]` |
| Inside a quoted field, `""` is one literal `"` | `'"a""b"'` → `['a"b']` |
| Non-ASCII content is fine | `'"café, x"'` → `["café, x"]` |
| Whitespace is significant, never trimmed | `" a , b "` → `[" a ", " b "]` |
| A quote anywhere else in an unquoted field is malformed | `'a"b'` → `ValueError` |
| A closing quote must be followed by `,` or end of input | `'"a"b'` → `ValueError` |
| A quoted field must be closed before the line ends | `'"a'` → `ValueError` |
| Carriage returns and newlines are not part of a record | `"a\nb"` → `ValueError` |

## Examples

| Call | Expected result |
| ---- | --------------- |
| `parse_csv_line("a,b,c")` | `["a", "b", "c"]` |
| `parse_csv_line("")` | `[""]` |
| `parse_csv_line("a,")` | `["a", ""]` |
| `parse_csv_line(",a")` | `["", "a"]` |
| `parse_csv_line('a,"b,c",d')` | `["a", "b,c", "d"]` |
| `parse_csv_line('"a""b"')` | `['a"b']` |
| `parse_csv_line('"a",')` | `["a", ""]` |
| `parse_csv_line('"a\\"')` | raises `ValueError` |

## Constraints

* Standard library only.
* Every failure mode above raises `ValueError` — never return a best-effort
  guess, and never drop characters silently.
* `line` is always a `str`.
* The number of fields always equals the number of top-level commas plus one.

## Hints

<details>
<summary>Hint 1 — Index walking beats split</summary>

`line.split(",")` cannot see the difference between a separator and a comma
inside quotes. Walk the string with an index instead and decide at each
position whether you are reading an unquoted field or a quoted one:

```python
i = 0
while i < len(line):
    if line[i] == '"':
        ...  # quoted branch
    else:
        ...  # unquoted branch
```

</details>

<details>
<summary>Hint 2 — Closing a quoted field</summary>

Two `""` in a row are an escape, not the end of the field. Only a `"` that is
*not* followed by another `"` closes the field — and the next character must
then be `,` or the end of the line:

```python
if line[i] == '"':
    if i + 1 < len(line) and line[i + 1] == '"':
        buffer.append('"')
        i += 2
        continue
    i += 1
    if i < len(line) and line[i] != ",":
        raise ValueError("unexpected text after closing quote")
    break
```

</details>
