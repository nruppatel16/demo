"""Tests for SDK->domain conversions (no network; duck-typed fakes)."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace

from algotrader.broker.alpaca_paper import (
    _SIDE_TO_ALPACA,
    to_account,
    to_clock,
    to_order,
    to_position,
)
from algotrader.broker.models import OrderSide


def test_to_account_uses_decimal():
    raw = SimpleNamespace(
        cash="1000.50", equity="1500.25", buying_power="3000.00", currency="USD"
    )
    acct = to_account(raw)
    assert acct.cash == Decimal("1000.50")
    assert acct.equity == Decimal("1500.25")
    assert acct.buying_power == Decimal("3000.00")
    assert acct.currency == "USD"


def test_to_position():
    raw = SimpleNamespace(
        symbol="SPY", qty="3", avg_entry_price="450.10", market_value="1350.30"
    )
    pos = to_position(raw)
    assert pos.symbol == "SPY"
    assert pos.qty == Decimal("3")
    assert pos.avg_entry_price == Decimal("450.10")


def test_to_order_handles_enum_like_fields():
    raw = SimpleNamespace(
        id="abc-123",
        symbol="SPY",
        qty="1",
        side=SimpleNamespace(value="buy"),
        status=SimpleNamespace(value="accepted"),
        submitted_at=datetime(2026, 6, 4, tzinfo=timezone.utc),
    )
    order = to_order(raw)
    assert order.id == "abc-123"
    assert order.side is OrderSide.BUY
    assert order.status == "accepted"


def test_to_clock():
    now = datetime(2026, 6, 4, 14, 30, tzinfo=timezone.utc)
    raw = SimpleNamespace(
        timestamp=now, is_open=True, next_open=now, next_close=now
    )
    clock = to_clock(raw)
    assert clock.is_open is True
    assert clock.timestamp == now


def test_side_mapping_covers_all_sides():
    # Every domain side must map to an SDK side.
    for side in OrderSide:
        assert side in _SIDE_TO_ALPACA
