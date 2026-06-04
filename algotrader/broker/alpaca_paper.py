"""Alpaca PAPER broker implementation.

This is the only concrete :class:`Broker`. It hardwires ``paper=True`` and never
exposes a live/real-money endpoint. There is deliberately no parameter, flag, or
code path that would route orders to a funded account.

SDK surface verified against alpaca-py 0.43.x:
  - TradingClient(api_key, secret_key, paper=True)
  - get_account() / get_all_positions() / get_open_position(symbol)
  - submit_order(order_data=MarketOrderRequest(...))
  - cancel_order_by_id(order_id) / close_position(symbol) / get_clock()
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide as AlpacaOrderSide
from alpaca.trading.enums import TimeInForce
from alpaca.trading.requests import MarketOrderRequest

from algotrader.broker.base import Broker
from algotrader.broker.models import (
    Account,
    Clock,
    Order,
    OrderRequest,
    OrderSide,
    Position,
)


def _dec(value: Any) -> Decimal:
    """Convert a broker numeric field (str/float/Decimal) to ``Decimal``."""
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


# --- SDK -> domain conversions (pure; duck-typed for easy unit testing) ------


def to_account(raw: Any) -> Account:
    return Account(
        cash=_dec(raw.cash),
        equity=_dec(raw.equity),
        buying_power=_dec(raw.buying_power),
        currency=str(raw.currency),
    )


def to_position(raw: Any) -> Position:
    return Position(
        symbol=str(raw.symbol),
        qty=_dec(raw.qty),
        avg_entry_price=_dec(raw.avg_entry_price),
        market_value=_dec(raw.market_value),
    )


def to_order(raw: Any) -> Order:
    side = raw.side.value if hasattr(raw.side, "value") else str(raw.side)
    return Order(
        id=str(raw.id),
        symbol=str(raw.symbol),
        qty=_dec(raw.qty),
        side=OrderSide(side),
        status=raw.status.value if hasattr(raw.status, "value") else str(raw.status),
        submitted_at=raw.submitted_at,
    )


def to_clock(raw: Any) -> Clock:
    return Clock(
        timestamp=raw.timestamp,
        is_open=bool(raw.is_open),
        next_open=raw.next_open,
        next_close=raw.next_close,
    )


_SIDE_TO_ALPACA = {
    OrderSide.BUY: AlpacaOrderSide.BUY,
    OrderSide.SELL: AlpacaOrderSide.SELL,
}


class AlpacaPaperBroker(Broker):
    """Concrete paper broker backed by Alpaca's paper trading API."""

    def __init__(self, api_key: str, secret_key: str) -> None:
        # paper=True is hardwired. Do NOT add a live switch here.
        self._client = TradingClient(api_key, secret_key, paper=True)

    def get_account(self) -> Account:
        return to_account(self._client.get_account())

    def get_positions(self) -> list[Position]:
        return [to_position(p) for p in self._client.get_all_positions()]

    def get_position(self, symbol: str) -> Position | None:
        from alpaca.common.exceptions import APIError

        try:
            return to_position(self._client.get_open_position(symbol))
        except APIError:
            # Alpaca returns 404 when there is no open position for the symbol.
            return None

    def submit_order(self, request: OrderRequest) -> Order:
        order_data = MarketOrderRequest(
            symbol=request.symbol,
            qty=float(request.qty),
            side=_SIDE_TO_ALPACA[request.side],
            time_in_force=TimeInForce.DAY,
        )
        return to_order(self._client.submit_order(order_data=order_data))

    def cancel_order(self, order_id: str) -> None:
        self._client.cancel_order_by_id(order_id)

    def close_position(self, symbol: str) -> Order:
        return to_order(self._client.close_position(symbol))

    def get_clock(self) -> Clock:
        return to_clock(self._client.get_clock())
