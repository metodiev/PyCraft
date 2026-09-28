# Generators, Lazy Pipelines and Memory

A generator is a function that produces values on demand instead of building a
collection. That single change — when work happens — is what lets a pipeline run over a
file larger than memory. It also introduces the sharpest new failure mode in this part of
the language: a generator is a one-shot iterator, and the second pass over it silently
yields nothing.

## The iterator protocol

`for x in obj` is sugar over a two-method protocol. `iter(obj)` calls `obj.__iter__()` and
must return an iterator; the iterator's `__next__()` returns the next value or raises
`StopIteration`, which is how the loop knows to stop.

```python
class Countdown:
    def __init__(self, start):
        self.current = start

    def __iter__(self):
        return self                      # this object is its own iterator

    def __next__(self):
        if self.current <= 0:
            raise StopIteration
        self.current -= 1
        return self.current + 1
```

An iterable has `__iter__`; an iterator has both. A list is iterable but not an iterator,
which is why `next([1, 2])` is a `TypeError` and `next(iter([1, 2]))` works. The
distinction matters because `for` calls `iter()` once at the start: an object whose
`__iter__` returns `self` tracks position, so a second loop over it continues where the
first stopped rather than restarting.

An exception raised inside a generator body propagates to the caller, with one special
case: `StopIteration` is converted to a `RuntimeError` by PEP 479, because a
`StopIteration` leaked from a helper call would otherwise look like the generator
finishing early. Use `return` to end a generator, never `raise StopIteration`.

## yield and lazy evaluation

Any function containing `yield` becomes a generator function. Calling it runs no code at
all: it returns a generator object, and the body starts executing only at the first
`next()`.

```python
def squares(n):
    for i in range(n):
        yield i * i          # suspend here, resume here on the next next()

squares(5)                   # <generator object squares> — nothing computed yet
list(squares(5))             # [0, 1, 4, 9, 16]
```

Each `yield` suspends the frame with its locals intact and hands one value to the caller.
Nothing accumulates unless the caller accumulates it, so a generator over an infinite
source is fine as long as something downstream stops asking:

```python
import itertools

def naturals():
    n = 0
    while True:
        yield n
        n += 1

list(itertools.islice(naturals(), 5))     # [0, 1, 2, 3, 4]
```

This is the memory argument. A list comprehension over a million rows builds a million row objects before the consumer sees the first one; the generator equivalent holds one row at a time — O(n) memory versus O(1). `sum(x * x for x in data)` and `sum([x * x for x in data])` agree on the answer, but the first never materialises the intermediate list.

Laziness has a cost: errors surface at consumption time, not where the pipeline was assembled, so a typo in the third stage of a five-stage pipeline raises inside whatever loop finally pulls on it.

## Single use

This is the trap that produces mysterious empty results:

```python
gen = (n * 2 for n in range(3))
sum(gen)      # 6
sum(gen)      # 0  — already exhausted, and no error is raised
```

The generator object holds the state; `sum()` consumed it. A list would restart because iterating a list creates a fresh iterator each time. Rules that follow:

1. A loop body that consumes the same generator twice needs a materialised list.
2. A function should not iterate an iterable parameter twice; call `list(items)` at the top if you need two passes, or accept a `Sequence` and say so in the type.
3. Returning a generator from a function that releases resources in a `finally` block makes cleanup non-deterministic: it runs when the generator is closed or garbage-collected, which may be much later — or never, at interpreter shutdown. Use a context manager instead.

Generators also support `send()` and `close()`. `close()` raises `GeneratorExit` at the suspension point, which is what gives a `try`/`finally` around a `yield` a chance to release resources when the consumer stops early.

## yield from

`yield from iterable` delegates to a sub-iterable, forwarding values (and `send()` and
`throw()` in both directions). It replaces a nested loop and is more efficient than one,
because it passes the sub-iterator directly to the caller:

```python
def inner():
    yield 1
    yield 2

def outer():
    yield 0
    yield from inner()
    yield from range(3, 5)

list(outer())     # [0, 1, 2, 3, 4]
```

Since 3.3, `yield from` is also how a `return value` inside a generator is delivered: the value lands on the `StopIteration` object raised when the generator finishes.

## Building a pipeline over a large input

Compose one generator per stage, each pulling from the previous. Nothing runs until the
outermost consumer asks, and memory stays proportional to the largest batch, not the file:

```python
def read_rows(path):
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.rstrip("\r\n")
            if line:
                yield line

def parse(row):
    return [field.strip() for field in row.split(",")]

def keep(rows, wanted):
    for row in rows:
        if row[0] in wanted:        # 'wanted' is a set: built once, looked up in O(1)
            yield row

def batches(rows, size):
    batch = []
    for row in rows:
        batch.append(row)
        if len(batch) == size:
            yield batch
            batch = []              # rebind, do not clear: the yielded list is the caller's
    if batch:                       # the final short batch is easy to forget
        yield batch

rows = read_rows("data.csv")
filtered = keep((parse(row) for row in rows), {"a", "b"})
for batch in batches(filtered, 500):
    handle(batch)
```

Three details in that snippet carry real weight. The file is never read whole; the `for
line in fh` loop reads incrementally. `batch = []` rebinds the name, so the list already
handed to the caller is not mutated after the fact — `batch.clear()` instead would blank
out every batch the consumer has stored. And the trailing `if batch:` prevents the last
partial batch from being dropped, the most common bug in hand-written batching code.

The `if row[0] in wanted` test is where the previous tutorial in this track pays off:
`wanted` must be a `set`, or each row costs a scan over every accepted key.

## Practice

[Lazy Batch Pipeline](../challenges/python-professional-lazy-batch-pipeline) asks you to
stream an iterable into batches and map chunks without ever materialising the source.

<details><summary>Hint: the final batch and the batch buffer</summary>

Yield a batch when it fills and again after the source is exhausted — but only if it is
non-empty. Do not wrap the input in `list()`, and rebind the batch list rather than
clearing it, so a batch the caller still holds is not emptied underneath them.

</details>
