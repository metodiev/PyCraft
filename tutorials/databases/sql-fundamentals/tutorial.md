# SQL Fundamentals: Joins, Aggregates and NULL

SQL looks like English, which is exactly why it misleads: you read a query top to bottom, but the engine evaluates it in a completely different order. Almost every "the query returned the wrong rows" bug traces back to that mismatch, or to the three-valued logic sitting underneath `NULL`.

## The logical order of evaluation

A `SELECT` statement is evaluated in this order, not the order you typed it:

1. `FROM` — build the working set, including joins
2. `WHERE` — filter individual rows
3. `GROUP BY` — collapse rows into groups
4. `HAVING` — filter groups
5. `SELECT` — compute the output columns, including aliases and window functions
6. `ORDER BY` — sort the result
7. `LIMIT` / `OFFSET` — take a slice

Two consequences fall directly out of this. First, a `SELECT` alias is usually not usable in `WHERE`, because the alias does not exist yet — PostgreSQL rejects `WHERE total > 5` when `total` is defined as `SUM(amount) AS total`. SQLite accepts it as a non-standard extension, which is a portability trap rather than a licence to rely on it. Second, `WHERE` runs before aggregation, so you cannot filter on an aggregate there; that is what `HAVING` is for.

```sql
SELECT customer_id, COUNT(*) AS orders, SUM(total) AS revenue
FROM orders
WHERE status = 'shipped'
GROUP BY customer_id
HAVING SUM(total) > 500
ORDER BY revenue DESC
LIMIT 10;
```

The rule of thumb: a predicate about *one row* belongs in `WHERE`; a predicate about *a group* belongs in `HAVING`. Putting a row-level predicate in `HAVING` is not merely stylistic. It forces the engine to aggregate rows that will be discarded, and — more dangerously — ungrouped column references in `HAVING` are resolved to an arbitrary row of the group, so `HAVING status = 'shipped'` on a group mixing statuses silently means "the status of whichever row the engine picked". Some engines reject that; SQLite and MySQL will happily return an answer whose meaning depends on execution order.

## Joins: inner, left and the shape of missing rows

An inner join keeps only pairs that match. A left join keeps every row from the left side and fills unmatched right-hand columns with `NULL`. That fill-in behaviour is the whole point, and also the trap.

```sql
SELECT c.name, o.id AS order_id
FROM customers c
LEFT JOIN orders o ON o.customer_id = c.id
WHERE o.id IS NULL;   -- customers with no orders
```

Move that `IS NULL` test into the `ON` clause and you get a different query. `LEFT JOIN orders o ON o.customer_id = c.id AND o.id IS NULL` matches no right-hand rows at all, so every customer survives once with `NULL` order columns — not just the ones without orders. Conditions in `ON` decide which pairs form; conditions in `WHERE` decide which of the resulting rows survive. For an outer join those are not the same question, and getting it wrong yields plausible-looking but wrong rows rather than an error.

A second trap: a left join followed by a `WHERE` predicate on the right-hand table silently degrades the join back to an inner join, because `NULL` comparisons are not true.

## Three-valued logic

SQL predicates evaluate to `TRUE`, `FALSE` or `UNKNOWN`. `NULL` means "value not known", and any comparison with it produces `UNKNOWN`. `WHERE` keeps only rows where the predicate is `TRUE`; `UNKNOWN` rows are dropped exactly like `FALSE` ones.

This breaks the two intuitions developers carry in from other languages:

- `NULL = NULL` is `UNKNOWN`, not true. Nothing equals an unknown value, not even itself. Use `IS NULL`, never `= NULL`.
- `WHERE col <> 5` does not return rows where `col` is `NULL`. Both `col = 5` and `col <> 5` are `UNKNOWN` for a null `col`, so the row disappears from either query.

```sql
-- Returns only rows where col is missing, not "not equal to 5".
SELECT * FROM readings WHERE value IS NULL;

-- Explicitly include the nulls when you want them.
SELECT * FROM readings WHERE value IS NULL OR value <> 5;
```

`NOT IN` is a sharper edge: if the subquery returns even one `NULL`, `x NOT IN (1, 2, NULL)` is `UNKNOWN` (or `FALSE`) for every row and the query returns nothing. `NOT EXISTS` does not have this problem, which is a good reason to prefer it.

`AND` and `OR` keep working with three values: `TRUE OR UNKNOWN` is `TRUE`, but `TRUE AND UNKNOWN` is `UNKNOWN`. `COALESCE(col, 0)` and `col IS DISTINCT FROM 5` (where supported) give you a total logic when you genuinely need one.

## COUNT and other aggregate quirks

`COUNT(*)` counts rows. `COUNT(col)` counts rows where `col` is not null. They differ exactly by the number of nulls in that column, which is the usual explanation for a "my counts disagree" investigation.

```sql
SELECT
  COUNT(*)                    AS all_orders,
  COUNT(shipped_at)           AS shipped,   -- NULL until shipped, so skipped
  COUNT(DISTINCT customer_id) AS customers
FROM orders;
```

The same rule applies to every aggregate except `COUNT(*)`: `SUM`, `AVG`, `MIN` and `MAX` ignore nulls. `AVG(col)` therefore divides by the number of non-null values, not by the row count — often the arithmetic you want, occasionally not. And `SUM` over zero non-null rows returns `NULL`, not `0`; wrap it in `COALESCE` if the caller expects a number.

## Practice

Work through the [SQL WHERE Compiler](../challenges/databases-sql-where-compiler) challenge: you build a small predicate evaluator with real three-valued logic, which is the fastest way to internalise why `WHERE col <> 5` drops rows. Before you start, try predicting the output of these two queries by hand and then check yourself:

```sql
SELECT COUNT(*) FROM t WHERE x <> 5;
SELECT COUNT(*) FROM t WHERE x IS NULL;
```

When you are comfortable with the evaluation order, move on to [Indexes, Query Plans and the Cost of a Scan](../tutorials/databases-indexes-and-query-plans) to see how these predicates change what the engine has to read.
