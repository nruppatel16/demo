"""SMA crossover strategy.

Per-symbol: long (weight = 1.0) when the fast SMA is above the slow SMA;
flat (weight = 0.0) otherwise. Stays in cash until enough history exists to
compute the slow SMA.

All computation is strictly causal: only bars already in the DataFrame are
used. No future prices can affect the signal at bar t.
"""

from __future__ import annotations

import pandas as pd

from algotrader.strategy.base import Strategy


class SmaCrossover(Strategy):
    """Parameterized SMA-crossover. Cash when fast SMA <= slow SMA."""

    def __init__(self, fast_window: int = 20, slow_window: int = 50) -> None:
        if fast_window >= slow_window:
            raise ValueError(
                f"fast_window ({fast_window}) must be < slow_window ({slow_window})"
            )
        self.fast_window = fast_window
        self.slow_window = slow_window
        self.name = f"sma_{fast_window}_{slow_window}"

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> dict[str, float]:
        signals: dict[str, float] = {}
        for sym, df in bars.items():
            if df.empty or len(df) < self.slow_window:
                signals[sym] = 0.0
                continue
            close = df["close"]
            fast_sma = float(close.iloc[-self.fast_window:].mean())
            slow_sma = float(close.iloc[-self.slow_window:].mean())
            signals[sym] = 1.0 if fast_sma > slow_sma else 0.0
        return signals
