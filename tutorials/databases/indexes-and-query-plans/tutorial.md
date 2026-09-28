# Indexes, Query Plans and the Cost of a Scan

An index is a data structure that lets the engine skip rows instead of reading them. Everything else — the write cost, the prefix rules, the covering index — follows from how that structure is ordered and how the planner decides it is cheaper than a full scan.

## What a B-tree index stores

A B-tree index on `(created_at)` stores the indexed keys in sorted order, each linked to the physical location of its row (in PostgreSQL, a heap tuple id; in SQLite, a rowid). Because the keys are sorted, the engine can descend the tree in a handful of page reads to reach the first matching key, then walk forward. A full table scan has to read every page of the table; a seek reads a logarithmic number of index pages plus the matching heap pages.

That difference is why an index turns a `WHERE id = 42` lookup from O(rows) into O(log rows), and why the win is largest when a highly selective predicate matches few rows. A predicate matching 60% of the table is usually cheaper to answer by scanning, because the index path degenerates into reading most of the table anyway, in a less friendly order.

Every index is also a second copy of its key columns, kept sorted, and that is a cost the query you are optimising never shows you:

- Each `INSERT`, `UPDATE` of an indexed column, and `DELETE` must also modify every affected index, so writes slow down roughly in proportion to the number of indexes.
- Index pages compete for the buffer pool with table pages, so a table with six indexes effectively has a smaller cache.
- Indexes consume disk and backup volume permanently.

The practical rule is that an index is cheap when it serves a real query pattern and expensive when added speculatively. After deleting a slow query, delete the index that existed only for it.

## Functions and casts defeat the index

An index on `created_at` cannot answer `WHERE date(created_at) = '2024-01-01'`. The index is ordered by `created_at`; the predicate asks about `date(created_at)`, which is a different, unsorted value that must be computed for every row. Postgres and SQLite have no way to map "date equals this" back to a range of timestamps, so both fall back to a scan.

```sql
-- Scan: the function is applied to the indexed column
SELECT * FROM events WHERE date(created_at) = '2024-01-01';

-- Seek: the indexed column stands alone against a range
SELECT * FROM events
WHERE created_at >= '2024-01-01'
  AND created_at <  '2024-01-02';
```

The same reasoning applies to casts (`WHERE id::text = '42'`) and to arithmetic (`WHERE amount * 100 > 5000`). Rewrite the predicate so the indexed column is untouched, or build an expression index on the exact expression you filter by — Postgres supports `CREATE INDEX ON events (date(created_at))`, and the planner will use it only when the predicate matches the expression exactly.

## Composite indexes and column order

An index on `(tenant_id, status, created_at)` is sorted by `tenant_id` first, then by `status` within each tenant, then by `created_at`. It can serve `WHERE tenant_id = ?`, `WHERE tenant_id = ? AND status = ?` and `WHERE tenant_id = ? AND status = ? AND created_at > ?`. It cannot serve `WHERE status = ?` alone the way those are served, because the index is not ordered by status globally; the values are scattered across tenants.

This is the leftmost-prefix rule: a composite index is usable for a prefix of its columns, and once you skip a column, the remaining ones can still filter inside the index but no longer drive the seek. SQLite and recent PostgreSQL can emulate a skipped leading column with a *skip scan* — read the distinct leading values and probe each — but that only pays off when the leading column has very few distinct values and the planner has statistics. Do not design around it; pick the column order from your query shapes.

Column order is therefore an API decision. Equality columns first, range or sort column last: a range in the middle stops the index driving a seek for anything after it.

A special case worth knowing is the covering index. If an index contains every column the query needs, the engine answers from the index alone with no heap fetch per row, removing the random I/O that dominates an index scan over many matches. Postgres calls this an index-only scan and you write it with the `INCLUDE` clause; in SQLite the same effect comes from a multi-column index. When `EXPLAIN` says `USING COVERING INDEX`, that is what happened.

```sql
-- PostgreSQL
CREATE INDEX orders_customer_covering
  ON orders (customer_id) INCLUDE (total, status);
```

A covering index for a hot query is one of the few legitimate reasons to duplicate columns in an index. The cost is the usual one: more pages to write on every insert and update, and more space.

## Reading an EXPLAIN plan

You do not need to read a full plan tree; you need to answer one question — is this a scan or a seek? In SQLite, `EXPLAIN QUERY PLAN` spells it out:

```bash
SCAN orders                                             # full table scan, every row read
SEARCH orders USING INDEX idx_customer (customer_id=?)  # index seek
SEARCH orders USING COVERING INDEX idx_covers (tenant_id=?, status=?)
```

In Postgres, look for the node type: `Seq Scan` is a full scan, `Index Scan` and `Index Only Scan` are seeks. Two further things are worth noticing. `Bitmap Heap Scan` means the planner collected matching index entries first and deduplicated page accesses — good for medium selectivity, a step away from a scan. And an `estimated rows` count that is wildly off from reality means stale statistics, which is a common cause of the planner choosing a scan for a query that should seek.

## Practice

Look at [MVCC Visibility](../challenges/databases-mvcc-visibility), which exercises the version chains an index entry ultimately points at. Then take a slow query in your own schema, run its plan, and rewrite the predicate until the plan reports a seek rather than a scan. If no rewrite is possible, an expression index on exactly the filtered expression is the remaining option — at the usual write cost.
