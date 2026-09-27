# Dedupe, Preserving Order

`set(items)` removes duplicates — and destroys the order. Real pipelines need
both: unique elements, in the order they first appeared.

## Your task

Complete the function `dedupe(items)` so it returns a **new list** containing
each distinct element of `items` exactly once, ordered by **first occurrence**.

Rules:

* Duplicates are decided by Python equality (`==`), exactly like the `in`
  operator. `1` and `1.0` are therefore duplicates; `1` and `"1"` are not.
* The **first** occurrence is the one that is kept (same object, same position).
* Elements may be **unhashable** — lists, dicts, sets — so a plain `set()` is
  not enough; the call must still work.
* The input list must **not** be modified.

## Examples

| Call | Expected result |
| ---- | --------------- |
| `dedupe([])` | `[]` |
| `dedupe([1, 2, 1, 3, 2])` | `[1, 2, 3]` |
| `dedupe(["b", "a", "b"])` | `["b", "a"]` |
| `dedupe([1, 1.0, 2])` | `[1, 2]` |
| `dedupe([[1], [1], [2]])` | `[[1], [2]]` |

## Constraints

* `items` is a `list`; it may be empty and may mix types.
* Return a `list` whose length is between `0` and `len(items)`.
* Only the elements are deduplicated — nested content is compared, not copied.

## Hints

<details>
<summary>Hint 1 — Why `set()` explodes</summary>

```python
>>> set([[1], [2]])
TypeError: unhashable type: 'list'
```

`set` needs hashable elements. An `in` check on a plain list uses `==`, which
works for *every* object, hashable or not.
</details>

<details>
<summary>Hint 2 — Hybrid approach for speed</summary>

You can keep a `set` for hashable values and fall back to a list scan for the
rest, but a single "seen" list with `if item not in seen:` is a perfectly good
solution at interview scale.
</details>
