"""Buy-and-hold benchmark strategy.

Always allocates equally across all symbols. This is the required benchmark
against which every other strategy is measured.

Note on survivorship bias: the symbols passed in are chosen by the user *now*,
which may exclude historically-failed securities. Users should be aware that
backtesting on a hand-picked universe of known survivors inflates results.
"""

from __future__ import annotations

import pandas as pd

from algotrader.strategy.base import Strategy


class BuyAndHold(Strategy):
    """Equal-weight allocation across the universe; never changes."""

    name = "buy_and_hold"

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> dict[str, float]:
        active = [sym for sym, df in bars.items() if not df.empty]
        if not active:
            return {}
        weight = 1.0 / len(active)
        return {sym: weight for sym in active}
