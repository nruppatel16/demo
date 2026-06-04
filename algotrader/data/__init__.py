"""Market-data module.

This module is the single source of truth for *what data existed at time T*.
Backtests and the live loop both pull bars from here, so they see identical data
for identical (symbol, timeframe, time) inputs.
"""

from algotrader.data.client import MarketDataClient
from algotrader.data.cache import BarCache

__all__ = ["MarketDataClient", "BarCache"]
