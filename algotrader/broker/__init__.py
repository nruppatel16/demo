"""Broker abstraction layer.

The :class:`~algotrader.broker.base.Broker` interface is defined purely in terms
of the broker-agnostic domain models in :mod:`algotrader.broker.models`. Swapping
in a different broker later should be a one-file change (a new implementation of
``Broker``) with nothing else in the codebase touched.

Only a PAPER implementation (``AlpacaPaperBroker``) exists. There is no live path.
"""

from algotrader.broker.base import Broker
from algotrader.broker.models import (
    Account,
    Clock,
    Order,
    OrderRequest,
    OrderSide,
    Position,
)

__all__ = [
    "Broker",
    "Account",
    "Clock",
    "Order",
    "OrderRequest",
    "OrderSide",
    "Position",
]
