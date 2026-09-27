"""SQLite persistence and the atomic checkout transaction.

This module owns storage and nothing else: it persists a ``Breakdown`` that has
already been computed. It must not do money arithmetic.

Tests import ``Product``, ``Receipt``, ``Store`` and
``InsufficientStockError`` from here.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

from pricing import Breakdown

SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    sku         TEXT PRIMARY KEY,
    name        TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    stock       INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id     TEXT PRIMARY KEY,
    subtotal     INTEGER NOT NULL,
    discount     INTEGER NOT NULL,
    taxable      INTEGER NOT NULL,
    tax          INTEGER NOT NULL,
    total        INTEGER NOT NULL,
    created_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS order_lines (
    order_id         TEXT NOT NULL,
    sku              TEXT NOT NULL,
    unit_price_cents INTEGER NOT NULL,
    quantity         INTEGER NOT NULL,
    line_total       INTEGER NOT NULL,
    PRIMARY KEY (order_id, sku)
);
"""


@dataclass(frozen=True)
class Product:
    sku: str
    name: str
    price_cents: int
    stock: int


@dataclass(frozen=True)
class Receipt:
    order_id: str
    breakdown: Breakdown
    lines: tuple[tuple[str, int, int, int], ...]  # (sku, unit_price, qty, line_total)
    created_at: datetime


class InsufficientStockError(RuntimeError):
    """Raised when a line cannot be fulfilled from stock."""

    def __init__(self, sku: str, requested: int, available: int) -> None:
        super().__init__(f"{sku}: requested {requested}, only {available} in stock")
        self.sku = sku
        self.requested = requested
        self.available = available


class Store:
    """A SQLite-backed catalogue and order book."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self._connection = sqlite3.connect(self.path)
        self._connection.row_factory = sqlite3.Row
        self._connection.executescript(SCHEMA)
        self._connection.commit()

    def close(self) -> None:
        self._connection.close()

    # --- catalogue -------------------------------------------------------
    def add_product(self, sku: str, name: str, price_cents: int, stock: int) -> None:
        """Insert or replace a product."""
        # TODO: implement.
        raise NotImplementedError

    def get_product(self, sku: str) -> Product | None:
        """Return the product, or ``None`` when the sku is unknown."""
        # TODO: implement.
        raise NotImplementedError

    def set_stock(self, sku: str, stock: int) -> None:
        """Set an absolute stock level (used by tests and admin tooling)."""
        # TODO: implement.
        raise NotImplementedError

    # --- orders ----------------------------------------------------------
    def place_order(self, order_id: str, lines: Iterable[tuple[str, int]], breakdown: Breakdown) -> Receipt:
        """Persist an order and decrement stock, all or nothing.

        Every line's stock is checked inside one ``BEGIN IMMEDIATE``
        transaction. If any line is short, the transaction rolls back and the
        database is left exactly as it was.
        """
        # TODO: open the transaction, check every line, write, commit once.
        raise NotImplementedError

    def get_order(self, order_id: str) -> Receipt | None:
        """Return a stored order, or ``None``."""
        # TODO: implement.
        raise NotImplementedError

    def stock_of(self, sku: str) -> int:
        """Current stock for a sku; 0 when the sku is unknown."""
        # TODO: implement.
        raise NotImplementedError

    def order_count(self) -> int:
        """How many orders have been committed."""
        # TODO: implement.
        raise NotImplementedError
