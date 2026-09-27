"""Hidden tests — the money and integrity details that matter in production."""

import sqlite3

import pytest

from pricing import Breakdown, discount_cents, line_total, price_order, subtotal, tax_cents
from service import CartLine, UnknownProductError, checkout
from store import InsufficientStockError, Store


@pytest.fixture()
def store(tmp_path):
    store = Store(tmp_path / "shop.db")
    store.add_product("pen", "Pen", 250, 10)
    store.add_product("book", "Book", 1500, 3)
    yield store
    store.close()


# --- exactness: the float trap -------------------------------------------
def test_money_never_touches_float():
    """0.1 + 0.2 != 0.3; a ledger cannot afford that."""
    total = 0
    for _ in range(10):
        total += line_total(10, 1)

    assert total == 100
    assert isinstance(total, int)


def test_subtotal_of_many_small_lines_is_exact():
    lines = [(1, 1)] * 1000

    assert subtotal(lines) == 1000


def test_results_are_always_integers():
    breakdown = price_order([(333, 3)], percent=7, fixed=11, tax_rate_bp=1750)

    for value in (
        breakdown.subtotal,
        breakdown.discount,
        breakdown.taxable,
        breakdown.tax,
        breakdown.total,
    ):
        assert isinstance(value, int), value


# --- rounding: half up, not banker's -------------------------------------
def test_tax_rounds_half_up():
    """round() would give 2 here; tax expects 3."""
    assert tax_cents(25, 1000) == 3


def test_tax_rounds_down_below_half():
    assert tax_cents(24, 1000) == 2


def test_tax_rounds_up_above_half():
    assert tax_cents(26, 1000) == 3


def test_tax_half_up_holds_over_a_range():
    """Sweep the .5 boundary; banker's rounding fails half of these."""
    assert tax_cents(5, 1000) == 1  # 0.5 -> 1
    assert tax_cents(15, 1000) == 2  # 1.5 -> 2
    assert tax_cents(45, 1000) == 5  # 4.5 -> 5
    assert tax_cents(55, 1000) == 6  # 5.5 -> 6


def test_a_zero_rate_is_free():
    assert tax_cents(9999, 0) == 0


# --- discount composition -------------------------------------------------
def test_discount_is_floored_not_rounded():
    """9% of 999 is 89.91; the customer cannot be credited a part cent."""
    assert discount_cents(999, percent=9) == 89


def test_discount_can_never_exceed_the_subtotal():
    """A big coupon makes the order free, never negative."""
    assert discount_cents(500, fixed=100_000) == 500


def test_discount_is_never_negative():
    assert discount_cents(500) == 0


def test_percent_is_applied_before_the_fixed_amount():
    """Applying fixed first changes the percentage's base."""
    assert discount_cents(1000, percent=50, fixed=100) == 600


def test_a_free_order_has_no_tax():
    breakdown = price_order([(1000, 1)], fixed=1000, tax_rate_bp=2000)

    assert breakdown.discount == 1000
    assert breakdown.taxable == 0
    assert breakdown.tax == 0
    assert breakdown.total == 0


def test_tax_applies_after_the_discount_not_before():
    """Taxing the gross subtotal is the classic accounting bug."""
    breakdown = price_order([(1000, 1)], percent=50, tax_rate_bp=2000)

    assert breakdown.subtotal == 1000
    assert breakdown.taxable == 500
    assert breakdown.tax == 100
    assert breakdown.total == 600


def test_the_breakdown_always_adds_up():
    for lines, percent, fixed, rate in (
        ([(333, 7)], 13, 47, 1975),
        ([(1, 1)], 0, 0, 1),
        ([(9999, 3)], 33, 999, 1234),
        ([(250, 4), (1500, 2)], 5, 100, 800),
    ):
        breakdown = price_order(lines, percent=percent, fixed=fixed, tax_rate_bp=rate)
        assert breakdown.subtotal - breakdown.discount == breakdown.taxable
        assert breakdown.taxable + breakdown.tax == breakdown.total


# --- atomicity: the whole point ------------------------------------------
def test_a_partially_fulfillable_order_changes_nothing(store):
    """The first line fits; the second does not. Nothing may be written."""
    stock_before = store.stock_of("pen")

    with pytest.raises(InsufficientStockError):
        checkout(store, "order-1", [CartLine("pen", 1), CartLine("book", 99)])

    assert store.stock_of("pen") == stock_before
    assert store.stock_of("book") == 3
    assert store.order_count() == 0
    assert store.get_order("order-1") is None


def test_stock_never_goes_negative(store):
    for index in range(3):
        checkout(store, f"ok-{index}", [CartLine("book", 1)])

    assert store.stock_of("book") == 0
    with pytest.raises(InsufficientStockError):
        checkout(store, "too-many", [CartLine("book", 1)])

    assert store.stock_of("book") == 0


def test_no_orphan_lines_after_a_failed_order(tmp_path):
    """A rolled-back order must not leave rows in order_lines."""
    path = tmp_path / "shop.db"
    store = Store(path)
    store.add_product("book", "Book", 1500, 3)

    with pytest.raises(InsufficientStockError):
        checkout(store, "order-1", [CartLine("book", 99)])
    store.close()

    observer = sqlite3.connect(path)
    count = observer.execute("SELECT COUNT(*) FROM order_lines").fetchone()[0]
    observer.close()

    assert count == 0


def test_a_rolled_back_order_is_not_visible_to_a_second_connection(tmp_path):
    """The rollback must actually be committed, not just abandoned."""
    path = tmp_path / "shop.db"
    store = Store(path)
    store.add_product("book", "Book", 1500, 1)

    with pytest.raises(InsufficientStockError):
        checkout(store, "order-1", [CartLine("book", 99)])
    store.close()

    observer = sqlite3.connect(path)
    orders = observer.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    stock = observer.execute("SELECT stock FROM products WHERE sku = 'book'").fetchone()[0]
    observer.close()

    assert orders == 0
    assert stock == 1


def test_stock_survives_a_reopen(tmp_path):
    path = tmp_path / "shop.db"
    store = Store(path)
    store.add_product("pen", "Pen", 250, 5)
    checkout(store, "order-1", [CartLine("pen", 2)])
    store.close()

    reopened = Store(path)
    assert reopened.stock_of("pen") == 3
    assert reopened.get_order("order-1") is not None
    reopened.close()


# --- idempotency ----------------------------------------------------------
def test_a_repeated_order_does_not_decrement_twice(store):
    checkout(store, "order-1", [CartLine("pen", 3)])
    checkout(store, "order-1", [CartLine("pen", 3)])

    assert store.stock_of("pen") == 7


def test_a_repeated_order_keeps_the_original_price(store):
    """Re-pricing on replay would let a price change alter a settled order."""
    original = checkout(store, "order-1", [CartLine("pen", 1)])

    store.add_product("pen", "Pen", 9999, 10)

    replayed = checkout(store, "order-1", [CartLine("pen", 1)])

    assert replayed.breakdown.subtotal == original.breakdown.subtotal == 250


def test_idempotency_beats_a_now_impossible_cart(store):
    """The order already exists, so a later stock shortage is irrelevant."""
    first = checkout(store, "order-1", [CartLine("book", 3)])

    replay = checkout(store, "order-1", [CartLine("book", 3)])

    assert replay == first
    assert store.stock_of("book") == 0


def test_idempotency_survives_a_reopen(tmp_path):
    path = tmp_path / "shop.db"
    store = Store(path)
    store.add_product("pen", "Pen", 250, 5)
    first = checkout(store, "order-1", [CartLine("pen", 2)])
    store.close()

    reopened = Store(path)
    replay = checkout(reopened, "order-1", [CartLine("pen", 2)])

    assert replay.breakdown.total == first.breakdown.total
    assert reopened.stock_of("pen") == 3
    reopened.close()


# --- validation -----------------------------------------------------------
def test_a_cart_quantity_above_stock_is_rejected_before_writing(store):
    before = store.order_count()

    with pytest.raises(InsufficientStockError):
        checkout(store, "order-1", [CartLine("pen", 11)])

    assert store.order_count() == before
    assert store.stock_of("pen") == 10


def test_a_negative_quantity_is_rejected(store):
    with pytest.raises(ValueError):
        checkout(store, "order-1", [CartLine("pen", -1)])


def test_a_single_unknown_sku_aborts_the_whole_order(store):
    stock_before = store.stock_of("pen")

    with pytest.raises(UnknownProductError):
        checkout(store, "order-1", [CartLine("pen", 1), CartLine("nope", 1)])

    assert store.stock_of("pen") == stock_before
    assert store.order_count() == 0


def test_the_receipt_records_every_line(store):
    receipt = checkout(store, "order-1", [CartLine("pen", 2), CartLine("book", 1)])

    skus = {line[0] for line in receipt.lines}
    assert skus == {"pen", "book"}
    assert receipt.breakdown.subtotal == 2000


def test_the_receipt_totals_match_the_lines(store):
    receipt = checkout(store, "order-1", [CartLine("pen", 2), CartLine("book", 1)])

    assert sum(line[3] for line in receipt.lines) == receipt.breakdown.subtotal


def test_the_store_rejects_an_oversell_without_the_service_layer(store):
    """The constraint belongs to the database, not only to the service."""
    breakdown = price_order([(1500, 99)])

    with pytest.raises(InsufficientStockError):
        store.place_order("order-1", [("book", 99)], breakdown)

    assert store.stock_of("book") == 3


def test_placing_an_order_twice_through_the_store_raises(store):
    """A duplicate primary key must surface, not silently double-charge."""
    breakdown = price_order([(250, 1)])
    store.place_order("order-1", [("pen", 1)], breakdown)

    with pytest.raises(sqlite3.IntegrityError):
        store.place_order("order-1", [("pen", 1)], breakdown)

    assert store.stock_of("pen") == 9


def test_an_empty_breakdown_is_still_persisted(store):
    """A zero-value order is unusual but must round-trip."""
    store.place_order("order-1", [], Breakdown(0, 0, 0, 0, 0))

    receipt = store.get_order("order-1")
    assert receipt is not None
    assert receipt.breakdown.total == 0
