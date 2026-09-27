# SQL WHERE Compiler

`WHERE` is where a query stops being a string and starts being logic — and
three-valued logic at that: `NULL` is not `False`, and `NULL = NULL` is neither
`True` nor `False`. Build the tiny compiler that turns the clause into a
predicate and evaluates it.

## Your task

Implement `compile_where(clause)` and `select(rows, clause)`.

### `compile_where(clause)`

Return a **callable** `predicate(row) -> bool` for the clause, where `row` is a
`dict`.

Grammar (whitespace-flexible, all keywords case-insensitive):

```
clause      := comparison (("AND" | "OR") comparison)*
comparison  := column ("=" | "!=" | "<" | "<=" | ">" | ">=") literal
             | "NOT" comparison
literal     := integer | 'single-quoted string' | NULL | TRUE | FALSE
```

* `AND` binds tighter than `OR` (so `a = 1 OR b = 2 AND c = 3` is
  `a = 1 OR (b = 2 AND c = 3)`).
* Parentheses may group comparisons and are handled with normal precedence.
* Values in `row` are compared using the operator; a comparison against `NULL`
  is never `True`.
* Comparing numbers to numbers uses numeric order; if either side is a `str`,
  compare as strings; mixed `int`/`str` comparisons are never `True` (except
  `!=`, which is then `True`).
* A syntax error raises `ValueError`, including: an unknown operator, an
  unterminated quoted string, trailing tokens, an empty clause, and unbalanced
  parentheses.

### Three-valued logic

`row.get(column)` may be missing or explicitly `None`. Treat both as `NULL`, and
evaluate each comparison to `True`, `False` or `None`:

| Expression | Result when either side is NULL |
| ---------- | ------------------------------ |
| `x = NULL`, `x = y` (with a NULL operand) | `None` |
| `x != NULL` | `None` |
| `x < NULL`, `x >= NULL`, … | `None` |
| `x = literal` where the column is missing and the literal is not NULL | `None` |
| `x IS NULL` / `x IS NOT NULL` | always `True`/`False`, never `None` |

`NOT NULL` is `NULL`; `NULL AND FALSE` is `False`; `NULL OR TRUE` is `True`.
Only a final result of exactly `True` counts as a match.

### `select(rows, clause)`

Return the rows for which the compiled predicate is `True`, preserving order.

## Examples

```python
rows = [
    {"id": 1, "name": "ada", "age": 36},
    {"id": 2, "name": "grace", "age": None},
    {"id": 3, "name": "linus", "age": 54},
]

select(rows, "age > 40")                      # [row 3]
select(rows, "age IS NULL")                   # [row 2]
select(rows, "age != 36")                     # [row 3]  (row 2 is NULL -> not a match)
select(rows, "name = 'ada' OR age > 50")      # [row 1, row 3]
select(rows, "age > 30 AND age < 40")         # [row 1]
select(rows, "NOT (age > 40)")                # [row 1]  (row 2 -> NOT NULL -> NULL)
select(rows, "name = 'ada' OR age > 50 AND id = 3")   # [row 1, row 3]
```

## Constraints

* Standard library only (`re` and `shlex` are allowed, but the string-quoting
  rules here are simple enough to hand-roll).
* `select` must not mutate `rows` or the row dicts.
* `compile_where` must be pure: the returned callable may be reused for many
  rows and must not depend on evaluation order.
* Column names match `[A-Za-z_][A-Za-z0-9_]*`; unquoted string literals are not
  allowed (single quotes are required).

## Hints

<details>
<summary>Hint 1 — Tokenise first, evaluate recursively</summary>

Two small passes beat one clever one. Turn the clause into a token list
(`IDENT`, `OP`, number, string, `NULL`, `TRUE`, `FALSE`, `AND`, `OR`, `NOT`,
`(`, `)`), then write a tiny recursive-descent parser:

```
expr    := term (OR term)*
term    := factor (AND factor)*
factor  := "NOT" factor | "(" expr ")" | comparison
```

Each parse function returns a callable; combining them is just
`lambda row: left(row) and right(row)` — but remember three-valued logic, so a
plain `and` on `None` is wrong. Normalise with a helper that maps `None` to
`None` explicitly.

</details>

<details>
<summary>Hint 2 — A 3-valued AND/OR table</summary>

Write the truth tables as functions instead of relying on Python's `and`/`or`,
which use truthiness:

```python
def _and(a, b):
    if a is False or b is False:
        return False
    if a is None or b is None:
        return None
    return True

def _or(a, b):
    if a is True or b is True:
        return True
    if a is None or b is None:
        return None
    return False

def _not(a):
    return None if a is None else not a
```

For a comparison, resolve the column with `row.get(column)` and, if either
operand is `None` and the operator is not `IS NULL`/`IS NOT NULL`, return `None`
before any comparison.
</details>
