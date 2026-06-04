"""Abstract broker interface.

Every method is defined in terms of the broker-agnostic models in
:mod:`algotrader.broker.models`. Implementations must not leak SDK-specific
types across this boundary.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from algotrader.broker.models import Account, Clock, Order, OrderRequest, Position


class Broker(ABC):
    """Interface for placing/inspecting orders against a (paper) account."""

    @abstractmethod
    def get_account(self) -> Account:
        """Return current account-level state (cash, equity, buying power)."""

    @abstractmethod
    def get_positions(self) -> list[Position]:
        """Return all currently open positions."""

    @abstractmethod
    def get_position(self, symbol: str) -> Position | None:
        """Return the open position for ``symbol``, or ``None`` if flat."""

    @abstractmethod
    def submit_order(self, request: OrderRequest) -> Order:
        """Submit a market order and return the resulting order record."""

    @abstractmethod
    def cancel_order(self, order_id: str) -> None:
        """Cancel an open (unfilled) order by id."""

    @abstractmethod
    def close_position(self, symbol: str) -> Order:
        """Liquidate the entire open position in ``symbol``."""

    @abstractmethod
    def get_clock(self) -> Clock:
        """Return the market clock (open/closed, next open/close)."""
