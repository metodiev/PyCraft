# MVCC Visibility

PostgreSQL never overwrites a row: every update writes a **new version** and
hides the old one from anyone whose snapshot predates the change. That single
idea gives readers a stable view without blocking writers — and it is why
`SELECT` in one transaction does not see another transaction's uncommitted work.

Implement the visibility rule and the write conflict it implies.

## Your task

Implement `Store` with these methods:

| Method | Behaviour |
| ------ | --------- |
| `begin()` | Start a transaction, returning a **monotonically increasing `int` id** starting at `1`. |
| `write(tx, key, value)` | Stage a new version of `key` for transaction `tx`. Raises `ValueError` for an unknown, committed or aborted transaction. |
| `read(tx, key)` | Return the value visible to `tx`, or `None` if no version is visible. |
| `commit(tx)` | Make the transaction's staged versions visible to later snapshots. |
| `abort(tx)` | Discard the transaction's staged versions. |
| `status(tx)` | One of `"active"`, `"committed"`, `"aborted"`, or `"unknown"`. |

### Versions

Each write appends a version `(key, value, commit_seq)` to a per-key list when
its transaction commits, where `commit_seq` comes from a global counter that
starts at `0` and increments on **every** commit.

A version is **visible** to transaction `tx` when `commit_seq <= snapshot(tx)`,
where `snapshot(tx)` is that counter's value at the moment `tx` began. Reads
always see committed state plus the reader's own uncommitted writes — never
another transaction's uncommitted writes.

The version chosen for a read is the one with the largest `commit_seq` among the
visible versions. Note the consequence: a transaction that committed *after* the
reader's snapshot took effect stays invisible to that reader even though its
transaction id is lower.

### Write conflicts

At most one **active** transaction may write a given key. A second active
transaction attempting to write that key raises `ValueError` — this is the
first-writer-wins guard that stops a lost update. After the first writer
commits or aborts, the key is writable again.

## Examples

```python
store = Store()
alice = store.begin()          # 1
store.write(alice, "x", 10)
bob = store.begin()            # 2
store.read(bob, "x")           # None  — alice has not committed
store.commit(alice)
store.read(bob, "x")           # None  — bob's snapshot predates alice's commit
carol = store.begin()          # 3
store.read(carol, "x")         # 10
```

## Constraints

* Standard library only.
* `commit(tx)` and `abort(tx)` on an unknown or already-finished transaction
  raise `ValueError`; `status` never raises (it returns `"unknown"`).
* `read` on an unknown transaction id raises `ValueError`, and so does `read` on
  a committed or aborted one (a finished transaction has no snapshot).
* Two writers cannot both stage a value for one key: the second `write` raises
  `ValueError` **until** the first finishes.
* After `abort`, the key's visible value is whatever it was before.

## Hints

<details>
<summary>Hint 1 — A commit counter is the whole snapshot mechanism</summary>

Track, per transaction, the value of a global `_committed` counter **at the
moment the transaction began**:

```python
def begin(self):
    self._next_id += 1
    tx = self._next_id
    self._snapshots[tx] = self._committed          # everything <= this committed earlier
    self._status[tx] = "active"
    return tx
```

Then a version written by `writer` is visible to `tx` when
`writer == tx or writer <= self._snapshots[tx]` — plus the requirement that the
writer really is committed, so keep a `_status` map and check it.

</details>

<details>
<summary>Hint 2 — Tracking the active writer per key</summary>

Keep `self._active_writers: dict[str, int]`. `write` complains when the key is
already owned by a *different* active transaction, and releases the key in both
`commit` and `abort`:

```python
if self._active_writers.get(key) not in (None, tx):
    raise ValueError(f"key {key!r} is already being written by another transaction")
self._active_writers[key] = tx
```

Remember to release **only** the keys that this transaction actually wrote.
</details>
