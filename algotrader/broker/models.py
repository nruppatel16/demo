"""Broker-agnostic domain models.

These types are the *only* vocabulary the rest of the system uses to talk about
accounts, positions, and orders. Concrete brokers translate their SDK objects to
and from these. Money is represented with :class:`~decimal.Decimal` to avoid
float rounding error.

v1 scope: cash-account, long-only, market orders. No shorting / leverage /
options / crypto.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from enum import Enum


class OrderSide(str, Enum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True)
class Account:
    """Snapshot of account-level state."""

    cash: Decimal
    equity: Decimal
    buying_power: Decimal
    currency: str


@dataclass(frozen=True)
class Position:
    """An open long position in a single symbol."""

    symbol: str
    qty: Decimal
    avg_entry_price: Decimal
    market_value: Decimal


@dataclass(frozen=True)
class Clock:
    """Market clock state."""

    timestamp: datetime
    is_open: bool
    next_open: datetime
    next_close: datetime


@dataclass(frozen=True)
class OrderRequest:
    """A request to place a market order.

    v1 supports market, day, long-only orders only. ``qty`` is shares.
    """

    symbol: str
    qty: Decimal
    side: OrderSide


@dataclass(frozen=True)
class Order:
    """A submitted order, as returned by the broker."""

    id: str
    symbol: str
    qty: Decimal
    side: OrderSide
    status: str
    submitted_at: datetime | None
