# Project: E-commerce Order Engine

**This is a project, not a drill.** Three modules must cooperate — money
arithmetic, a transactional store and a checkout service — and the tests drive
them directly against a real SQLite database.

The interesting part is not "compute a total". It is that **money and stock are
the two places where sloppy code costs real money**, and both are unforgiving:

- money must be exact, so it lives in integer cents and never touches `float`;
- stock must never go negative, so checkout is all-or-nothing.

| File | Responsibility |
| ---- | -------------- |
| `pricing.py` | Pure arithmetic: line totals, discount composition, tax, rounding |
| `store.py` | SQLite persistence and the atomic checkout transaction |
| `service.py` | Orchestration: validation, idempotency, receipts |

## Your task

### `pricing.py`

All amounts are **integer cents**. No function here may import `sqlite3`.

| Name | Contract |
| ---- | -------- |
| `Breakdown` | Dataclass: `subtotal`, `discount`, `taxable`, `tax`, `total` |
| `line_total(unit_price_cents, quantity)` | `unit_price * quantity`; reject a negative price or a quantity below 1 |
| `subtotal(lines)` | Sum of `line_total` over `(unit_price_cents, quantity)` pairs |
| `discount_cents(subtotal_cents, *, percent=0, fixed=0)` | Percentage first, then the fixed amount; the result is floored, never negative, and **never exceeds the subtotal** |
| `tax_cents(taxable_cents, rate_bp)` | `rate_bp` is basis points (2000 = 20%); round **half up** |
| `price_order(lines, *, percent=0, fixed=0, tax_rate_bp=0)` | Compose the above into a `Breakdown` |

The order of operations is fixed and is the whole point:

```
subtotal = Σ line_total
discount = min(subtotal, floor(subtotal × percent / 100) + fixed)
taxable  = subtotal − discount
tax      = round_half_up(taxable × rate_bp / 10000)
total    = taxable + tax
```

Because Python's `round` is banker's rounding, `round(2.5) == 2`. That is wrong
for tax: 2.5 cents must round to 3.

### `store.py`

`Store(path)` opens (or creates) a SQLite database and creates its schema.

| Method | Contract |
| ------ | -------- |
| `add_product(sku, name, price_cents, stock)` | Insert or replace a product row |
| `get_product(sku)` | Return a `Product` or `None` |
| `set_stock(sku, stock)` | Set an absolute stock level |
| `place_order(order_id, lines, breakdown)` | Atomically apply an order |
| `get_order(order_id)` | Return a `Receipt` or `None` |

`place_order` must be **atomic**: it decrements every line's stock by checking
`stock >= quantity` *inside the transaction*, inserts the order and its lines,
and commits exactly once. If **any** line is short, nothing at all is written —
no order row, no stock change. Use `BEGIN IMMEDIATE` so the check and the
decrement cannot interleave.

Stock must never go below zero, and that must hold even when two orders are
placed in sequence where the second would oversell.

### `service.py`

| Name | Contract |
| ---- | -------- |
| `CartLine` | Dataclass: `sku`, `quantity` |
| `InsufficientStockError` | Raised when a line cannot be fulfilled |
| `UnknownProductError` | Raised for a sku that is not in the catalogue |
| `checkout(store, order_id, cart, *, percent=0, fixed=0, tax_rate_bp=0)` | Validate, price, persist, return a `Receipt` |

`checkout` must:

- reject an empty cart and a non-positive quantity;
- raise `UnknownProductError` for an unknown sku;
- raise `InsufficientStockError` when stock is short — **and leave stock and the
  order table untouched**;
- be **idempotent** on `order_id`: calling it again returns the stored receipt
  unchanged, with no second stock decrement and no re-pricing.

`Receipt` carries `order_id`, `breakdown`, `lines` and `created_at`.

## Examples

```pycon
>>> price_order([(1000, 2)], percent=10, fixed=100, tax_rate_bp=2000)
Breakdown(subtotal=2000, discount=300, taxable=1700, tax=340, total=2040)
```

## Constraints

- Standard library only, including `sqlite3`.
- `pricing.py` must not import `store.py` or `service.py`, and must not use
  floating point anywhere.
- `store.py` must not compute prices; it persists the `Breakdown` it is given.
- Money is integer cents everywhere. `Decimal` and `float` are both wrong here.

## Hints

<details>
<summary>Hint 1 — Rounding half up without floats</summary>

For `numerator / denominator` with the denominator positive:

```
q, r = divmod(numerator, denominator)
return q + (1 if 2 * r >= denominator else 0)
```

This never materialises a float, so it cannot drift.

</details>

<details>
<summary>Hint 2 — Why `BEGIN IMMEDIATE`</summary>

SQLite defers a write lock until the first write by default. With
`BEGIN IMMEDIATE` the lock is taken at `BEGIN`, so the `SELECT` that checks
stock and the `UPDATE` that decrements it cannot be separated by another
connection's write.

</details>

<details>
<summary>Hint 3 — Rollback covers the whole checkout</summary>

Open one transaction, check *every* line before writing anything, then write.
If you prefer to write as you go, wrap the whole thing in `try/except` and
`ROLLBACK` on failure — the tests assert that a failed checkout leaves the
database byte-for-byte unchanged in effect.

</details>

<details>
<summary>Hint 4 — Idempotency belongs in the transaction</summary>

Read the stored order *inside* the transaction that would create it. Checking
first and writing later leaves a window where two concurrent callers both see
"no order" and both charge.
</details>
