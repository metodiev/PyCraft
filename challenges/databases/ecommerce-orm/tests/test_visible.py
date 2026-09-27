"""Visible tests — the basic contract for each module."""

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


# --- pricing -------------------------------------------------------------
def test_line_total_multiplies_price_by_quantity():
    assert line_total(250, 3) == 750


def test_line_total_rejects_a_negative_price():
    with pytest.raises(ValueError):
        line_total(-1, 1)


def test_line_total_rejects_a_zero_quantity():
    with pytest.raises(ValueError):
        line_total(100, 0)


def test_subtotal_sums_the_lines():
    assert subtotal([(250, 2), (1500, 1)]) == 2000


def test_percentage_discount():
    assert discount_cents(2000, percent=10) == 200


def test_fixed_discount():
    assert discount_cents(2000, fixed=300) == 300


def test_percentage_then_fixed_are_summed():
    assert discount_cents(2000, percent=10, fixed=100) == 300


def test_tax_uses_basis_points():
    assert tax_cents(1000, 2000) == 200


def test_price_order_composes_the_breakdown():
    result = price_order([(1000, 2)], percent=10, fixed=100, tax_rate_bp=2000)

    assert result == Breakdown(subtotal=2000, discount=300, taxable=1700, tax=340, total=2040)


# --- store ---------------------------------------------------------------
def test_add_and_get_a_product(store):
    product = store.get_product("pen")

    assert product is not None
    assert product.name == "Pen"
    assert product.price_cents == 250
    assert product.stock == 10


def test_unknown_product_is_none(store):
    assert store.get_product("nope") is None


def test_stock_is_readable(store):
    assert store.stock_of("pen") == 10


def test_placing_an_order_decrements_stock(store):
    breakdown = price_order([(250, 2)])

    store.place_order("order-1", [("pen", 2)], breakdown)

    assert store.stock_of("pen") == 8
    assert store.order_count() == 1


def test_a_stored_order_can_be_read_back(store):
    breakdown = price_order([(250, 2)])
    store.place_order("order-1", [("pen", 2)], breakdown)

    receipt = store.get_order("order-1")

    assert receipt is not None
    assert receipt.order_id == "order-1"
    assert receipt.breakdown.total == 500


def test_unknown_order_is_none(store):
    assert store.get_order("nope") is None


def test_placing_an_order_beyond_stock_raises(store):
    breakdown = price_order([(250, 99)])

    with pytest.raises(InsufficientStockError):
        store.place_order("order-1", [("pen", 99)], breakdown)


# --- service -------------------------------------------------------------
def test_checkout_returns_a_receipt(store):
    receipt = checkout(store, "order-1", [CartLine("pen", 2)], tax_rate_bp=2000)

    assert receipt.order_id == "order-1"
    assert receipt.breakdown.subtotal == 500
    assert store.stock_of("pen") == 8


def test_checkout_uses_the_catalogue_price(store):
    receipt = checkout(store, "order-1", [CartLine("pen", 1)])

    assert receipt.breakdown.subtotal == 250


def test_checkout_rejects_an_unknown_sku(store):
    with pytest.raises(UnknownProductError):
        checkout(store, "order-1", [CartLine("nope", 1)])


def test_checkout_rejects_an_empty_cart(store):
    with pytest.raises(ValueError):
        checkout(store, "order-1", [])


def test_checkout_rejects_a_zero_quantity(store):
    with pytest.raises(ValueError):
        checkout(store, "order-1", [CartLine("pen", 0)])


def test_checkout_raises_when_stock_is_short(store):
    with pytest.raises(InsufficientStockError):
        checkout(store, "order-1", [CartLine("pen", 99)])


def test_placing_the_same_order_twice_is_idempotent(store):
    first = checkout(store, "order-1", [CartLine("pen", 2)])
    stock_after_first = store.stock_of("pen")

    second = checkout(store, "order-1", [CartLine("pen", 2)])

    assert second == first
    assert store.stock_of("pen") == stock_after_first
    assert store.order_count() == 1
