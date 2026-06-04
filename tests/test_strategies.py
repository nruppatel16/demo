"""Strategy unit tests (no network; synthetic data only)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd
import pytest

from algotrader.strategy.buy_and_hold import BuyAndHold
from algotrader.strategy.sma_crossover import SmaCrossover


def _bars(n: int, close_values=None, start="2022-01-01") -> pd.DataFrame:
    dates = pd.date_range(start, periods=n, freq="B")
    closes = close_values if close_values is not None else [100.0 + i for i in range(n)]
    return pd.DataFrame({
        "open": closes, "high": [c + 1 for c in closes],
        "low": [c - 1 for c in closes], "close": closes, "volume": [1000] * n,
    }, index=dates)


# --- BuyAndHold ---

def test_buy_and_hold_single_symbol():
    s = BuyAndHold()
    signals = s.generate_signals({"SPY": _bars(5)})
    assert signals == {"SPY": 1.0}


def test_buy_and_hold_equal_weight_multi():
    s = BuyAndHold()
    signals = s.generate_signals({"SPY": _bars(5), "QQQ": _bars(5), "AAPL": _bars(5)})
    for w in signals.values():
        assert abs(w - 1/3) < 1e-9
    assert abs(sum(signals.values()) - 1.0) < 1e-9


def test_buy_and_hold_empty_bars_skipped():
    s = BuyAndHold()
    signals = s.generate_signals({"SPY": _bars(5), "EMPTY": pd.DataFrame()})
    assert "EMPTY" not in signals or signals.get("EMPTY", 0) == 0
    assert "SPY" in signals


# --- SmaCrossover ---

def test_sma_crossover_flat_until_slow_window():
    s = SmaCrossover(fast_window=5, slow_window=10)
    for n in range(1, 10):
        signals = s.generate_signals({"SPY": _bars(n)})
        assert signals["SPY"] == 0.0, f"Expected flat at n={n}, got {signals['SPY']}"


def test_sma_crossover_long_when_fast_above_slow():
    # Rising series: fast SMA > slow SMA
    s = SmaCrossover(fast_window=5, slow_window=10)
    closes = list(range(1, 21))  # 1..20: fast SMA > slow SMA at the end
    signals = s.generate_signals({"SPY": _bars(20, closes)})
    assert signals["SPY"] == 1.0


def test_sma_crossover_flat_when_fast_below_slow():
    # Falling series: fast SMA < slow SMA
    s = SmaCrossover(fast_window=5, slow_window=10)
    closes = list(range(20, 0, -1))  # 20..1: fast SMA < slow SMA at the end
    signals = s.generate_signals({"SPY": _bars(20, closes)})
    assert signals["SPY"] == 0.0


def test_sma_crossover_rejects_invalid_windows():
    with pytest.raises(ValueError):
        SmaCrossover(fast_window=50, slow_window=20)

    with pytest.raises(ValueError):
        SmaCrossover(fast_window=20, slow_window=20)


def test_sma_crossover_name_encodes_params():
    s = SmaCrossover(fast_window=10, slow_window=30)
    assert "10" in s.name and "30" in s.name
