"""DuckDB-backed local cache for historical bars.

Stores OHLCV bars keyed by (symbol, timeframe, timestamp) so repeated backtests
don't re-hit the data API. Upserts are done as delete-in-range + insert, which is
dialect-agnostic and idempotent.
"""

from __future__ import annotations

import os
from datetime import datetime

import duckdb
import pandas as pd

_OHLCV = ["open", "high", "low", "close", "volume"]

_SCHEMA = """
CREATE TABLE IF NOT EXISTS bars (
    symbol     VARCHAR   NOT NULL,
    timeframe  VARCHAR   NOT NULL,
    ts         TIMESTAMP NOT NULL,
    open       DOUBLE,
    high       DOUBLE,
    low        DOUBLE,
    close      DOUBLE,
    volume     DOUBLE
);
"""


class BarCache:
    """Persistent cache of historical bars in a single DuckDB file."""

    def __init__(self, data_dir: str, filename: str = "market_data.duckdb") -> None:
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, filename)
        with duckdb.connect(self._path) as con:
            con.execute(_SCHEMA)

    def read(
        self, symbol: str, timeframe: str, start: datetime, end: datetime
    ) -> pd.DataFrame:
        """Return cached bars for ``symbol``/``timeframe`` within [start, end].

        Result is a DataFrame indexed by ``timestamp`` with OHLCV columns,
        sorted ascending. Empty if nothing is cached for the range.
        """
        with duckdb.connect(self._path) as con:
            df = con.execute(
                """
                SELECT ts AS timestamp, open, high, low, close, volume
                FROM bars
                WHERE symbol = ? AND timeframe = ? AND ts >= ? AND ts <= ?
                ORDER BY ts
                """,
                [symbol, timeframe, start, end],
            ).df()
        if not df.empty:
            df = df.set_index("timestamp")
        return df

    def write(self, symbol: str, timeframe: str, bars: pd.DataFrame) -> None:
        """Upsert ``bars`` (indexed by timestamp, OHLCV columns) into the cache."""
        if bars.empty:
            return

        frame = bars.reset_index()
        frame = frame.rename(columns={frame.columns[0]: "ts"})
        frame = frame[["ts", *_OHLCV]].copy()
        frame.insert(0, "symbol", symbol)
        frame.insert(1, "timeframe", timeframe)

        lo, hi = frame["ts"].min(), frame["ts"].max()
        with duckdb.connect(self._path) as con:
            con.register("incoming", frame)
            con.execute(
                """
                DELETE FROM bars
                WHERE symbol = ? AND timeframe = ? AND ts >= ? AND ts <= ?
                """,
                [symbol, timeframe, lo, hi],
            )
            con.execute("INSERT INTO bars SELECT * FROM incoming")
            con.unregister("incoming")
