"""DuckDB-backed persistence for backtest runs, live trades, and equity history.

Schema:
  runs          — one row per backtest/live session
  trades        — filled orders (backtest fill log or live paper orders)
  equity_curve  — daily equity snapshots
  metrics       — computed performance metrics keyed by run
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import duckdb

_DDL = """
CREATE TABLE IF NOT EXISTS runs (
    run_id        VARCHAR PRIMARY KEY,
    created_at    TIMESTAMP NOT NULL,
    strategy_name VARCHAR NOT NULL,
    symbols       VARCHAR,
    timeframe     VARCHAR,
    start_date    TIMESTAMP,
    end_date      TIMESTAMP,
    run_type      VARCHAR   -- 'backtest' | 'live'
);

CREATE TABLE IF NOT EXISTS trades (
    id            VARCHAR PRIMARY KEY,
    run_id        VARCHAR NOT NULL,
    ts            TIMESTAMP NOT NULL,
    strategy_name VARCHAR NOT NULL,
    symbol        VARCHAR NOT NULL,
    side          VARCHAR NOT NULL,
    shares        DOUBLE  NOT NULL,
    fill_price    DOUBLE,
    order_id      VARCHAR,
    slippage_bps  DOUBLE
);

CREATE TABLE IF NOT EXISTS equity_curve (
    run_id        VARCHAR NOT NULL,
    ts            TIMESTAMP NOT NULL,
    strategy_name VARCHAR NOT NULL,
    equity        DOUBLE NOT NULL,
    PRIMARY KEY (run_id, ts, strategy_name)
);

CREATE TABLE IF NOT EXISTS metrics (
    run_id        VARCHAR NOT NULL,
    strategy_name VARCHAR NOT NULL,
    metric_name   VARCHAR NOT NULL,
    metric_value  DOUBLE,
    PRIMARY KEY (run_id, strategy_name, metric_name)
);
"""


class TradeStorage:
    """Write and query the results database."""

    def __init__(self, data_dir: str, filename: str = "results.duckdb") -> None:
        os.makedirs(data_dir, exist_ok=True)
        self._path = os.path.join(data_dir, filename)
        self._run_id = str(uuid.uuid4())
        with duckdb.connect(self._path) as con:
            con.execute(_DDL)

    @property
    def run_id(self) -> str:
        return self._run_id

    def new_run(
        self,
        strategy_name: str,
        symbols: list[str],
        timeframe: str,
        run_type: str = "backtest",
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> str:
        self._run_id = str(uuid.uuid4())
        with duckdb.connect(self._path) as con:
            con.execute(
                """INSERT INTO runs VALUES (?,?,?,?,?,?,?,?)""",
                [
                    self._run_id,
                    datetime.now(timezone.utc),
                    strategy_name,
                    ",".join(symbols),
                    timeframe,
                    start_date,
                    end_date,
                    run_type,
                ],
            )
        return self._run_id

    def record_trades(
        self, trades: list, strategy_name: str, run_id: str | None = None
    ) -> None:
        """Bulk-insert backtest trade log."""
        rid = run_id or self._run_id
        rows = []
        for t in trades:
            rows.append([
                str(uuid.uuid4()), rid, t.timestamp, strategy_name,
                t.symbol, t.side, float(t.shares), float(t.fill_price),
                None, t.slippage_bps,
            ])
        if not rows:
            return
        with duckdb.connect(self._path) as con:
            con.executemany(
                "INSERT OR IGNORE INTO trades VALUES (?,?,?,?,?,?,?,?,?,?)", rows
            )

    def record_equity_series(
        self, equity_series: object, strategy_name: str, run_id: str | None = None
    ) -> None:
        """Bulk-insert a pandas Series of equity values."""
        import pandas as pd
        assert isinstance(equity_series, pd.Series)
        rid = run_id or self._run_id
        rows = [
            [rid, ts, strategy_name, float(val)]
            for ts, val in equity_series.items()
        ]
        with duckdb.connect(self._path) as con:
            con.executemany(
                "INSERT OR REPLACE INTO equity_curve VALUES (?,?,?,?)", rows
            )

    def record_metrics(
        self, metrics: dict[str, float], strategy_name: str, run_id: str | None = None
    ) -> None:
        rid = run_id or self._run_id
        rows = [[rid, strategy_name, k, v] for k, v in metrics.items()]
        with duckdb.connect(self._path) as con:
            con.executemany(
                "INSERT OR REPLACE INTO metrics VALUES (?,?,?,?)", rows
            )

    def record_order(
        self, strategy_name: str, symbol: str, side: str,
        shares: float, order_id: str
    ) -> None:
        """Record one live order."""
        with duckdb.connect(self._path) as con:
            con.execute(
                "INSERT INTO trades VALUES (?,?,?,?,?,?,?,?,?,?)",
                [
                    str(uuid.uuid4()), self._run_id,
                    datetime.now(timezone.utc), strategy_name,
                    symbol, side, shares, None, order_id, None,
                ],
            )

    def record_equity_snapshot(self, strategy_name: str, equity: float) -> None:
        ts = datetime.now(timezone.utc)
        with duckdb.connect(self._path) as con:
            con.execute(
                "INSERT OR REPLACE INTO equity_curve VALUES (?,?,?,?)",
                [self._run_id, ts, strategy_name, equity],
            )

    # --- Queries ---

    def list_runs(self, n: int = 10) -> object:
        with duckdb.connect(self._path) as con:
            return con.execute(
                "SELECT run_id, created_at, strategy_name, run_type, start_date, end_date "
                "FROM runs ORDER BY created_at DESC LIMIT ?",
                [n],
            ).df()

    def get_equity_curve(self, run_id: str, strategy_name: str) -> object:
        with duckdb.connect(self._path) as con:
            return con.execute(
                "SELECT ts, equity FROM equity_curve "
                "WHERE run_id=? AND strategy_name=? ORDER BY ts",
                [run_id, strategy_name],
            ).df()

    def get_metrics(self, run_id: str) -> object:
        with duckdb.connect(self._path) as con:
            return con.execute(
                "SELECT strategy_name, metric_name, metric_value "
                "FROM metrics WHERE run_id=? ORDER BY strategy_name, metric_name",
                [run_id],
            ).df()

    def get_trades(self, run_id: str) -> object:
        with duckdb.connect(self._path) as con:
            return con.execute(
                "SELECT * FROM trades WHERE run_id=? ORDER BY ts",
                [run_id],
            ).df()
