# Lists, Dicts and the Cost of Lookup

Two snippets can compute the same answer and differ by a factor of thousands in
running time, purely because one asked the wrong container a question. Choosing a
container is choosing which operations are cheap, so this tutorial starts from the
contracts and then looks at the lookup that trips up more interview candidates than
any other.

## Four containers, four contracts

| Container | Ordered | Duplicates | `x in c` | Best at |
| --------- | ------- | ---------- | -------- | ------- |
| `list` | yes | yes | O(n) scan | Positional data, stacking, sorting, slices |
| `tuple` | yes | yes | O(n) scan | Fixed-size records, returning several values, dict keys |
| `set` | no | no | O(1) average | Membership, deduplication, set algebra |
| `dict` | yes (3.7+) | unique keys | O(1) average | Labelled lookup, counting, grouping, records with schema |

The rules of thumb follow directly. Reach for a `tuple` when the number of elements is
part of the meaning — a coordinate is a pair, not a list that happens to have two
entries. Reach for a `set` when you care only whether something is present. Reach for a
`dict` when the position of a value is meaningless and you will look it up by name.

A `tuple` is also the cheapest immutable record: it has no per-instance `__dict__`,
unpacks positionally, and is hashable as long as everything inside it is hashable.

## Hashability, and why a list cannot be a key

`dict` keys and `set` members must be hashable, which means two things must hold:
the object's hash never changes during its lifetime, and equal objects have equal
hashes. Mutable containers cannot satisfy the first condition, so Python refuses them:

```python
d = {}
d[(1, 2)] = "fine"          # tuple of hashables
d[(1, [2])] = "no"          # TypeError: unhashable type: 'list'
d[[1, 2]] = "no"            # TypeError: unhashable type: 'list'
```

The failure is deliberate, not a limitation to work around: if a list key were allowed
and then mutated, its hash would change and lookups would silently stop finding it.
When you genuinely need a mutable value as a key, key on the immutable part —
an id, a `frozenset` of tags, or `tuple(sorted(items))`.

Two consequences bite in practice. A `dict` keyed by `list` fails at insert time, so
the error is loud; a `set` of records fails later, when the first duplicate insert is
attempted. And `==` is not `is`: two distinct tuples can be equal and therefore the
same key, which is exactly why deduplication works.

## The membership test inside a loop

This is the performance trap worth memorising. It is not wrong code, it is quadratic code:

```python
allowed_ids = [3, 7, 11, 42]        # a list

def keep(rows):
    return [row for row in rows if row.id in allowed_ids]
```

Each `in` walks the list until it finds a match or reaches the end. With *m* rows and *n*
allowed ids that is O(m × n) comparisons; growing the allow-list by ten doubles the
comparison count. Converting once to a `set` turns each test into an average O(1) hash
lookup, so the loop body no longer depends on the size of the allow-list:

```python
allowed_ids = {3, 7, 11, 42}        # a set: build it once, outside the loop

def keep(rows):
    return [row for row in rows if row.id in allowed_ids]
```

The O(1) is an average, not a promise. Hashing is not free, collisions degrade the
average towards O(n) in adversarial cases, and for a handful of elements a list scan is
genuinely faster than hashing because it avoids the hash computation. The rule that
matters: **materialise the set once, outside the loop**. Rebuilding it inside costs more
than the list scan you replaced.

## Dicts keep insertion order, and that is a guarantee

Since Python 3.7, `dict` iteration follows insertion order, and `set` order does not —
`set` ordering is an implementation detail that changes with the values stored. Dict
order is defined by the language, so you can rely on it for output and for
deduplication that preserves first appearance:

```python
def dedupe(items):
    return list(dict.fromkeys(items))
```

`dict.fromkeys` keeps the first insertion position of each key; later duplicates update
the value but do not move the key. It is the shortest correct dedupe for hashable
items. When items are unhashable — lists of lists, dicts — the same trick fails with
`TypeError`, and you need a seen-set of computed keys or an explicit accepted-list scan.

```python
def dedupe_by(items, key):
    seen = set()
    out = []
    for item in items:
        marker = key(item)
        if marker not in seen:
            seen.add(marker)
            out.append(item)
    return out
```

Also note that `==` between two dicts ignores order — comparison is by keys and values,
so `{"a": 1, "b": 2} == {"b": 2, "a": 1}` is `True`. Order matters for output, not
for equality.

## Comprehensions versus loops

A comprehension is not only shorter, it is measurably faster: the loop runs inside the
interpreter without a name lookup for `append` per iteration, and the result list is
allocated with a known growth strategy. It also gets its own scope, so the target name
does not leak into the surrounding function:

```python
pairs = [n for n in numbers if n % 2 == 0]        # list
lengths = {word: len(word) for word in words}     # dict
uniq = {letter for word in words for letter in word}   # set
```

Nested comprehensions read left to right like nested loops: the first `for` is the outer
one. Convert back to a plain loop when the body grows a `try`, an `if`/`elif` chain, more
than one statement, or a side effect. A comprehension with a function call for its
side effects is a bug in disguise — nothing forces it to be consumed until something
iterates it.

## Practice

Apply this material in [Dedupe, Preserving Order](../challenges/python-fundamentals-dedupe-preserving-order),
which asks you to remove duplicates while keeping first-occurrence order, including for
items a `set` cannot hold.

<details><summary>Hint: seen keys and output order</summary>

A set of seen keys gives the O(n) path; the accepted list gives the order. Keep them in
lockstep, and decide what "seen" means when the item is itself a list — a plain `set`
raises `TypeError` there.

</details>
