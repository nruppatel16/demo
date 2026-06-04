"""Bar-by-bar backtest engine.

No-look-ahead guarantee (provable):
    At bar index i, the strategy receives only bars[:i+1] for each symbol.
    Order fills use the NEXT bar's open price (index i+1), which is NOT in the
    visible slice. The test in tests/test_backtest.py proves this empirically
    with a sentinel-value approach.

Timing model (fills at next open):
    bar i CLOSE  -> run strategy on bars[0..i] -> queue orders
    bar i+1 OPEN -> fill queued orders at open[i+1] ± slippage
    bar i+1 CLOSE -> record equity; run strategy on bars[0..i+1] -> ...

Slippage is applied symmetrically:
    BUY  fill = open * (1 + slippage_bps / 10_000)
    SELL fill = open * (1 - slippage_bps / 10_000)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

import pandas as pd

from algotrader.backtest.portfolio import Portfolio, Trade
from algotrader.risk.manager import RiskManager
from algotrader.strategy.base import Strategy


@dataclass
class BacktestResult:
    strategy_name: str
    symbols: list[str]
    start_date: datetime
    end_date: datetime
    equity_curve: pd.Series          # DatetimeIndex -> float equity
    benchmark_equity: pd.Series      # BuyAndHold equity curve for same period
    trades: list[Trade]
    metrics: dict[str, float] = field(default_factory=dict)
    benchmark_metrics: dict[str, float] = field(default_factory=dict)


def _apply_slippage(price: float, side: str, bps: float) -> Decimal:
    factor = 1.0 + bps / 10_000 if side == "buy" else 1.0 - bps / 10_000
    return Decimal(str(round(price * factor, 4)))


class BacktestEngine:
    """Replay historical bars and track portfolio performance."""

    def __init__(
        self,
        bars: dict[str, pd.DataFrame],      # symbol -> OHLCV df, DatetimeIndex
        strategy: Strategy,
        risk_manager: RiskManager | None = None,
        initial_capital: float = 100_000.0,
        slippage_bps: float = 5.0,
        benchmark_strategy: Strategy | None = None,
    ) -> None:
        self._bars = bars
        self._strategy = strategy
        self._risk = risk_manager
        self._initial_capital = initial_capital
        self._slippage_bps = slippage_bps
        self._symbols = list(bars.keys())

        # Default benchmark is BuyAndHold (no risk management applied)
        if benchmark_strategy is None:
            from algotrader.strategy.buy_and_hold import BuyAndHold
            self._benchmark_strategy: Strategy = BuyAndHold()
        else:
            self._benchmark_strategy = benchmark_strategy

    def run(self) -> BacktestResult:
        common_index = self._common_index()
        if len(common_index) < 2:
            raise ValueError("Need at least 2 bars to run a backtest.")

        equity_curve = self._simulate(common_index, self._strategy, self._risk)
        benchmark_curve = self._simulate(common_index, self._benchmark_strategy, None)

        from algotrader.metrics.calculator import compute_metrics
        portfolio = self._last_portfolio
        benchmark_portfolio = self._last_benchmark_portfolio

        result = BacktestResult(
            strategy_name=self._strategy.name,
            symbols=self._symbols,
            start_date=common_index[0].to_pydatetime(),
            end_date=common_index[-1].to_pydatetime(),
            equity_curve=equity_curve,
            benchmark_equity=benchmark_curve,
            trades=portfolio.trades,
        )
        result.metrics = compute_metrics(equity_curve, benchmark_curve)
        result.benchmark_metrics = compute_metrics(benchmark_curve, benchmark_curve)
        return result

    def _common_index(self) -> pd.DatetimeIndex:
        """Intersection of all symbols' date indices, sorted."""
        if not self._bars:
            return pd.DatetimeIndex([])
        idx = None
        for df in self._bars.values():
            idx = df.index if idx is None else idx.intersection(df.index)
        return idx.sort_values()  # type: ignore[union-attr]

    def _simulate(
        self,
        common_index: pd.DatetimeIndex,
        strategy: Strategy,
        risk: RiskManager | None,
    ) -> pd.Series:
        """Run one simulation pass; return equity curve indexed by date."""
        portfolio = Portfolio.fresh(self._initial_capital)

        # Store for caller to inspect trades
        if strategy is self._strategy:
            self._last_portfolio = portfolio
        else:
            self._last_benchmark_portfolio = portfolio

        equity_values: dict = {}
        pending: list[tuple[str, Decimal]] = []  # (symbol, delta_shares) queued

        for i, ts in enumerate(common_index):
            # --- Fill yesterday's orders at today's open ---
            if pending and i > 0:
                for sym, delta in pending:
                    open_price = float(self._bars[sym].loc[ts, "open"])
                    if delta > 0:
                        fill = _apply_slippage(open_price, "buy", self._slippage_bps)
                        portfolio.execute_buy(sym, delta, fill, ts.to_pydatetime(), self._slippage_bps)
                    else:
                        fill = _apply_slippage(open_price, "sell", self._slippage_bps)
                        portfolio.execute_sell(sym, -delta, fill, ts.to_pydatetime(), self._slippage_bps)
                pending = []

            # --- Record equity at today's close ---
            close_prices = {sym: float(self._bars[sym].loc[ts, "close"]) for sym in self._symbols}
            equity_values[ts] = float(portfolio.equity(close_prices))

            # --- Run strategy on data strictly up to and including bar i ---
            # This slice is the fundamental no-look-ahead guarantee.
            # bars[:i+1] cannot contain bar i+1 because Python slice end is exclusive.
            visible = {sym: self._bars[sym].iloc[: i + 1] for sym in self._symbols}
            raw_signals = strategy.generate_signals(visible)

            # --- Apply risk rules (not applied to benchmark) ---
            if risk is not None:
                target_weights = risk.apply(raw_signals, portfolio, close_prices)
            else:
                target_weights = {sym: min(max(w, 0.0), 1.0) for sym, w in raw_signals.items()}

            # --- Convert weights -> share counts ---
            target_shares = portfolio.target_shares(target_weights, close_prices)

            # --- Compute deltas and queue for next-bar fill ---
            pending = portfolio.order_deltas(target_shares, self._symbols)

        equity_series = pd.Series(equity_values, name="equity")
        equity_series.index = pd.DatetimeIndex(equity_series.index)
        return equity_series
