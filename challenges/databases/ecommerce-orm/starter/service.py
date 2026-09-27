"""Checkout orchestration.

This module owns validation, pricing call order and idempotency. It is the only
place that knows about both money and storage.

Tests import ``CartLine``, ``UnknownProductError``, ``checkout`` and ``Receipt``
from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from pricing import price_order
from store import InsufficientStockError, Receipt, Store


class UnknownProductError(LookupError):
    """Raised for a sku that is not in the catalogue."""


@dataclass(frozen=True)
class CartLine:
    sku: str
    quantity: int


def checkout(
    store: Store,
    order_id: str,
    cart: Iterable[CartLine],
    *,
    percent: int = 0,
    fixed: int = 0,
    tax_rate_bp: int = 0,
) -> Receipt:
    """Validate, price and persist an order.

    Ordering matters:

    1. **Idempotency first** — an order that already exists is returned as-is,
       with no re-pricing and no second stock decrement.
    2. Validate the cart (non-empty, positive quantities, known skus).
    3. Price it from the *catalogue* unit prices, never from caller input.
    4. Persist atomically; a stock failure must leave nothing behind.
    """
    # TODO: implement in the order above.
    raise NotImplementedError
