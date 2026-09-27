# Lazy Batch Pipeline

Bulk endpoints like `POST /items/bulk`, database drivers and message brokers all
want work in **pages** rather than one item at a time. The naive implementation
— `list(iterable)` and slice it — is fine until the source is a log file with
ten million lines, a socket, or an endless stream of events.

## Your task

Implement two generators that never hold more than one batch in memory.

### `batches(iterable, size)`

Yield `list` objects, each holding up to `size` items from `iterable`, in order.
The final batch may be shorter. An empty source yields no batches at all.

* `size` must be an `int >= 1` — otherwise raise `ValueError` **from the call
  itself**, before any iteration happens. (`batches([1], 0)` must raise even
  though nobody iterated the result.)
* `iterable` may be any iterable, including an infinite one. Only pull the items
  a batch actually needs: obtaining the first batch of 3 from an infinite
  iterator must terminate.

### `take(iterable, n)`

Yield at most `n` items from the front of `iterable` — and pull no more than
`n` items from the source, even when the source has more.

* `n <= 0` yields nothing and pulls **nothing** from the source.
* Anything not yielded is untouched: the source iterator keeps whatever is left.

## Examples

| Call | Expected result |
| ---- | --------------- |
| `list(batches([1, 2, 3, 4, 5], 2))` | `[[1, 2], [3, 4], [5]]` |
| `list(batches([], 3))` | `[]` |
| `list(batches(range(4), 4))` | `[[0, 1, 2, 3]]` |
| `batches([1, 2], 0)` | raises `ValueError` immediately |
| `list(take([1, 2, 3, 4], 2))` | `[1, 2]` |
| `list(take([1, 2], 5))` | `[1, 2]` |
| `list(take([1, 2], 0))` | `[]` (nothing pulled) |

## Constraints

* Standard library only (`itertools` is allowed and encouraged).
* Both functions return **lazy** iterators. Building a list of all input first,
  or calling `len()`/indexing the source, is a contract violation — the hidden
  tests measure how many items are pulled from the source.
* The batches themselves are real `list` objects; assert equality with a list.

## Hints

<details>
<summary>Hint 1 — Validate first, then delegate lazily</summary>

A plain generator function does not execute its body until the first `next()`,
so `ValueError` would be raised too late. Validate in a normal function and
return an inner generator:

```python
def batches(iterable, size):
    if size < 1:
        raise ValueError("size must be >= 1")
    return _batches(iterable, size)      # _batches is the generator function
```

</details>

<details>
<summary>Hint 2 — Pulling exactly what you need</summary>

`itertools.islice` is the tool for "up to `size` more items, no more":

```python
iterator = iter(iterable)
while True:
    chunk = list(itertools.islice(iterator, size))
    if not chunk:
        return
    yield chunk
```

`islice(iterator, 0)` — which is what `take(source, 0)` reduces to — yields
nothing **and consumes nothing**, so the zero case falls out for free.
</details>
