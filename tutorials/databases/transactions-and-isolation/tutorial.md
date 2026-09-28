# Transactions, Isolation Levels and MVCC

Isolation levels are the knobs that decide which concurrency anomalies your database will let through, and MVCC is the mechanism most engines use to provide them. If you remember only one thing, remember that "read committed" and "serializable" are not the same guarantee — one permits write skew, the other rejects it at commit time.

## ACID without hand-waving

Atomicity means a transaction's writes become visible all at once or not at all; a crash mid-transaction leaves no partial state. Consistency means constraints hold at commit boundaries, enforced by the engine — a foreign key violation rolls back the statement or the transaction, depending on the engine and the setting. Durability means once the commit is acknowledged, the data survives a crash.

Isolation is the interesting one, because it is the only property that is a spectrum rather than a boolean. Perfect isolation — serializability — means the concurrent result equals some serial ordering of the transactions. Providing it strictly costs concurrency: transactions would have to take locks that block each other, so engines offer weaker levels that permit named anomalies in exchange for throughput.

## The anomalies

| Anomaly | What happens | Prevented by |
| ------- | ------------ | ------------ |
| Dirty read | You read an uncommitted write that may be rolled back | Read committed |
| Non-repeatable read | The same row returns different values twice in one transaction | Repeatable read |
| Phantom read | A re-run query returns new rows matching the predicate | Snapshot isolation (in most MVCC engines), serializable |
| Lost update | Two read-modify-write cycles overwrite each other | Row locks, or first-writer-wins conflict detection |
| Write skew | Two transactions each read a set, then write based on it, and together they break an invariant | Serializable only (and explicit locks on the shared set) |

Write skew is the one that surprises people, because every individual transaction is consistent. Suppose a constraint: at least one doctor must be on call. Two doctors, both logged in, each checks "how many are on call?" — both see 2 — and each sets their own flag to false. No row is written by both transactions, so row-level locking does not help and a uniqueness constraint does not apply. The result is zero doctors on call. Only serializable isolation, or an explicit lock on the shared set, prevents it.

## How MVCC gives readers a stable snapshot

Instead of overwriting a row in place, MVCC engines write a new version with metadata describing which transactions may see it. A transaction reads the version whose creator committed before its snapshot started and whose deleter had not committed by then. Readers never take shared locks on the data they read, so a long report never blocks an `UPDATE`, and a writer never makes a reader wait.

This is why a transaction that started earlier does not see a commit that happened later. Visibility is decided by comparing each version's transaction ids against the reader's snapshot, not by wall-clock time and not by numeric ordering of the ids. A later id can easily be invisible to a snapshot taken earlier, and an earlier id can be invisible to a snapshot taken later if it had not committed when that snapshot was taken.

```bash
tx 100 begins, takes a snapshot
tx 101 begins, updates account 7, commits
tx 100 reads account 7  # sees the pre-101 version: 101 had not committed
                        # when the snapshot was taken
```

An `UPDATE` in MVCC is not an in-place overwrite: it writes a new version and marks the old one deleted. That is why a writer which modifies a row that another transaction changed *after* its snapshot was taken must detect the conflict instead of applying the update blindly — under snapshot isolation it would otherwise silently clobber the newer version. This is first-writer-wins: the committed writer keeps its change, the other transaction gets a serialization failure or write conflict. The correct reaction is to retry the whole transaction, not to force the update through.

## Read committed is not serializable

Read committed takes a fresh snapshot for every statement, so a transaction can observe another transaction's commit midway through. In PostgreSQL, read committed does not give you a repeatable view at all: `SELECT` twice in one transaction and you can get different results. Repeatable read takes one snapshot for the whole transaction, which is what most people assume read committed means.

Even repeatable read is not serializable, as the write skew example shows — each transaction reads a consistent snapshot, and the snapshots just happen to be mutually inconsistent. Serializable adds predicate locks or equivalent conflict tracking, so a transaction that would produce a non-serializable outcome is aborted rather than committed. The runtime bill is real: more aborts, and application code that must handle them.

Practical guidance: use read committed for ordinary request handling and take explicit `SELECT ... FOR UPDATE` locks on the rows you read-modify-write. Use repeatable read for reports that need a stable view. Reach for serializable when an invariant spans multiple rows and the cost of a rare retry is less than the cost of a lost invariant.

## Practice

Work through [MVCC Visibility](../challenges/databases-mvcc-visibility), where you implement snapshot visibility and prove two writers cannot silently lose an update. Two things to watch: retries must rerun the whole transaction, including its reads, or you re-introduce lost updates; and a long-lived snapshot in an append-heavy table holds garbage versions alive, which is why long-running read transactions cause bloat.
