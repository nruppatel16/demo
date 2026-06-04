"""Market-data client: Alpaca historical bars + local DuckDB cache.

Returns a normalized OHLCV DataFrame (indexed by UTC timestamp) regardless of
source. The cache is consulted first; on a miss, bars are fetched from Alpaca and
written back.

Note on caching (Phase 1, intentionally simple): if the cache holds *any* rows in
the requested range it is treated as a hit. Precise gap-filling across partial
ranges is deferred to the backtest phase, where date ranges are fixed and large.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

from algotrader.data.cache import BarCache

# Maps our config string -> Alpaca TimeFrame.
_TIMEFRAMES: dict[str, TimeFrame] = {
    "1Min": TimeFrame(1, TimeFrameUnit.Minute),
    "5Min": TimeFrame(5, TimeFrameUnit.Minute),
    "15Min": TimeFrame(15, TimeFrameUnit.Minute),
    "1Hour": TimeFrame(1, TimeFrameUnit.Hour),
    "1Day": TimeFrame(1, TimeFrameUnit.Day),
}

_OHLCV = ["open", "high", "low", "close", "volume"]


def resolve_timeframe(name: str) -> TimeFrame:
    """Translate a config timeframe string to an Alpaca ``TimeFrame``."""
    try:
        return _TIMEFRAMES[name]
    except KeyError:
        raise ValueError(
            f"Unknown timeframe {name!r}; expected one of {sorted(_TIMEFRAMES)}"
        ) from None


class MarketDataClient:
    """Fetches historical bars, transparently caching them locally."""

    def __init__(
        self, api_key: str, secret_key: str, cache: BarCache | None = None
    ) -> None:
        self._client = StockHistoricalDataClient(api_key, secret_key)
        self._cache = cache

    def get_bars(
        self,
        symbol: str,
        timeframe: str,
        start: datetime,
        end: datetime,
        use_cache: bool = True,
    ) -> pd.DataFrame:
        """Return OHLCV bars for ``symbol`` in [start, end], indexed by timestamp."""
        if use_cache and self._cache is not None:
            cached = self._cache.read(symbol, timeframe, start, end)
            if not cached.empty:
                return cached

        bars = self._fetch(symbol, timeframe, start, end)

        if use_cache and self._cache is not None and not bars.empty:
            self._cache.write(symbol, timeframe, bars)
        return bars

    def _fetch(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=resolve_timeframe(timeframe),
            start=start,
            end=end,
        )
        barset = self._client.get_stock_bars(request)
        return self._normalize(barset.df, symbol)

    @staticmethod
    def _normalize(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
        """Flatten Alpaca's (symbol, timestamp) multi-index to OHLCV by timestamp."""
        if df is None or df.empty:
            return pd.DataFrame(columns=_OHLCV)

        # alpaca-py returns a MultiIndex of (symbol, timestamp).
        if isinstance(df.index, pd.MultiIndex):
            df = df.xs(symbol, level="symbol")

        df = df[[c for c in _OHLCV if c in df.columns]].copy()
        df.index.name = "timestamp"
        return df.sort_index()
