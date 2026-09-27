"""Exact money arithmetic.

Everything here is **integer cents**. Floating point is not permitted anywhere
in this module: ``0.1 + 0.2 != 0.3`` is amusing in a tutorial and a bug in a
ledger.

This module is pure — it must not import ``store`` or ``service``.

Tests import ``Breakdown``, ``discount_cents``, ``line_total``, ``price_order``,
``subtotal`` and ``tax_cents`` from here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

#: ``(unit_price_cents, quantity)``
Line = tuple[int, int]


@dataclass(frozen=True)
class Breakdown:
    """The money story of one order, in cents."""

    subtotal: int
    discount: int
    taxable: int
    tax: int
    total: int


def line_total(unit_price_cents: int, quantity: int) -> int:
    """Price one line.

    A negative unit price or a quantity below 1 is a programming error, not a
    customer action, so reject it with ``ValueError``.
    """
    # TODO: implement, rejecting nonsense inputs.
    raise NotImplementedError


def subtotal(lines: Iterable[Line]) -> int:
    """Sum the priced lines."""
    # TODO: implement.
    raise NotImplementedError


def discount_cents(subtotal_cents: int, *, percent: int = 0, fixed: int = 0) -> int:
    """Total discount for an order.

    The percentage is applied first, then the fixed coupon, and the two are
    summed. The result is floored to whole cents, is never negative, and can
    never exceed the subtotal — a coupon bigger than the order makes the order
    free, not negative.
    """
    # TODO: percentage first, then fixed; clamp into ``[0, subtotal]``.
    raise NotImplementedError


def tax_cents(taxable_cents: int, rate_bp: int) -> int:
    """Tax on a taxable amount, in basis points (2000 = 20%).

    Round **half up**. ``round`` cannot be used: it is banker's rounding, so
    ``round(2.5)`` is 2 where tax law expects 3.
    """
    # TODO: implement with integer arithmetic only.
    raise NotImplementedError


def price_order(
    lines: Iterable[Line],
    *,
    percent: int = 0,
    fixed: int = 0,
    tax_rate_bp: int = 0,
) -> Breakdown:
    """Compose the whole calculation.

    Discount applies to the subtotal; tax applies to what is left *after* the
    discount, never to the gross subtotal.
    """
    # TODO: compose subtotal -> discount -> taxable -> tax -> total.
    raise NotImplementedError
