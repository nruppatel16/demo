"""Backtest engine tests.

The most important test in this file is ``test_engine_has_no_lookahead_bias``.
It uses a sentinel-value approach to empirically prove that the engine never
leaks future prices to the strategy.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pandas as pd
import pytest

from algotrader.backtest.engine import BacktestEngine
from algotrader.backtest.portfolio import Portfolio, Trade
from algotrader.backtest.walk_forward import WalkForwardSplitter
from algotrader.strategy.base import Strategy
from algotrader.strategy.buy_and_hold import BuyAndHold
from algotrader.strategy.sma_crossover import SmaCrossover


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _bars(closes: list[float], start: str = "2020-01-01") -> pd.DataFrame:
    n = len(closes)
    dates = pd.date_range(start, periods=n, freq="B")
    return pd.DataFrame({
        "open": closes, "high": [c + 1 for c in closes],
        "low":  [c - 1 for c in closes], "close": closes, "volume": [1_000_000] * n,
    }, index=dates)


# ─── NO-LOOK-AHEAD TEST (prime directive) ─────────────────────────────────────

def test_engine_has_no_lookahead_bias():
    """
    Prove the backtest engine NEVER gives the strategy access to future data.

    Approach:
      1. Create a 25-bar synthetic price series where bar index 15 has an
         unmistakable sentinel close price (SENTINEL_PRICE = 99_999.0).
      2. Use a SpyStrategy that records the maximum close price it sees at
         each step (keyed by the number of bars in the slice it received).
      3. Assert: at every step i < 16, the sentinel was NEVER visible
         (the DataFrame slice did not yet include bar 15).
      4. Assert: at step 16 (i.e., len=16, meaning bars[0..15] are present),
         the sentinel IS visible — proving the test itself is meaningful and
         would catch a look-ahead if one existed.
    """
    SENTINEL_IDX   = 15
    SENTINEL_PRICE = 99_999.0
    N_BARS         = 25

    closes = [100.0 + i for i in range(N_BARS)]
    closes[SENTINEL_IDX] = SENTINEL_PRICE  # plant sentinel at index 15

    bars = _bars(closes)

    max_close_by_step: dict[int, float] = {}

    class SpyStrategy(Strategy):
        name = "spy"

        def generate_signals(self, data: dict) -> dict[str, float]:
            df = data["SPY"]
            n = len(df)
            max_close_by_step[n] = float(df["close"].max())
            return {"SPY": 0.0}   # always flat; we only care about the data seen

    engine = BacktestEngine(
        bars={"SPY": bars},
        strategy=SpyStrategy(),
        initial_capital=10_000.0,
        slippage_bps=0.0,
    )
    engine.run()

    # ── Assertion 1: before the sentinel bar is in the window, it's invisible ──
    for step in range(1, SENTINEL_IDX + 1):
        seen_max = max_close_by_step.get(step, 0.0)
        assert seen_max != SENTINEL_PRICE, (
            f"LOOK-AHEAD BIAS DETECTED: at step {step} (bars 0..{step-1}), "
            f"strategy saw sentinel price {SENTINEL_PRICE} which should not be "
            f"reachable until step {SENTINEL_IDX + 1}."
        )

    # ── Assertion 2: once bar SENTINEL_IDX enters the slice, it IS visible ──
    # (This proves the test would actually catch a look-ahead.)
    step_when_visible = SENTINEL_IDX + 1
    assert max_close_by_step.get(step_when_visible) == SENTINEL_PRICE, (
        f"TEST LOGIC ERROR: sentinel should be visible at step {step_when_visible} "
        f"but was not. Check SENTINEL_IDX and N_BARS."
    )


# ─── Engine smoke tests ───────────────────────────────────────────────────────

def test_engine_bah_fully_invests():
    """BuyAndHold should hold a position after the first bar."""
    bars = _bars([100.0] * 50)
    engine = BacktestEngine({"SPY": bars}, BuyAndHold(), initial_capital=10_000.0)
    result = engine.run()
    assert len(result.equity_curve) == 50
    # With a flat price, equity after first buy should stay near initial capital
    assert abs(result.equity_curve.iloc[-1] - 10_000.0) < 50  # small slippage drag


def test_engine_equity_curve_length_matches_bars():
    bars = _bars(list(range(1, 31)))
    engine = BacktestEngine({"SPY": bars}, BuyAndHold(), initial_capital=5_000.0)
    result = engine.run()
    assert len(result.equity_curve) == 30


def test_engine_rising_market_bah_beats_cash():
    closes = [100.0 + i for i in range(100)]
    bars = _bars(closes)
    engine = BacktestEngine({"SPY": bars}, BuyAndHold(), initial_capital=10_000.0)
    result = engine.run()
    assert result.equity_curve.iloc[-1] > 10_000.0


def test_engine_sma_flat_before_slow_window():
    """SmaCrossover stays flat for the first slow_window bars → equity = initial capital."""
    bars = _bars([100.0] * 60)
    sma = SmaCrossover(fast_window=5, slow_window=20)
    engine = BacktestEngine({"SPY": bars}, sma, initial_capital=10_000.0, slippage_bps=0.0)
    result = engine.run()
    # First 20 equity points should be exactly initial capital (in cash, no fills)
    for val in result.equity_curve.iloc[:20]:
        assert val == pytest.approx(10_000.0, rel=1e-6), f"Expected cash, got {val}"


def test_engine_raises_on_too_few_bars():
    bars = _bars([100.0])
    with pytest.raises(ValueError):
        BacktestEngine({"SPY": bars}, BuyAndHold()).run()


def test_engine_metrics_present():
    bars = _bars([100.0 + i for i in range(100)])
    result = BacktestEngine({"SPY": bars}, BuyAndHold(), initial_capital=10_000.0).run()
    for key in ("total_return", "cagr", "sharpe", "max_drawdown", "volatility"):
        assert key in result.metrics


# ─── Portfolio unit tests ─────────────────────────────────────────────────────

def test_portfolio_equity_no_positions():
    p = Portfolio.fresh(50_000.0)
    assert float(p.equity({"SPY": 450.0})) == pytest.approx(50_000.0)


def test_portfolio_buy_reduces_cash():
    p = Portfolio.fresh(10_000.0)
    ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
    p.execute_buy("SPY", Decimal("10"), Decimal("100.00"), ts)
    assert float(p.cash) == pytest.approx(9_000.0)
    assert p.positions["SPY"] == Decimal("10")


def test_portfolio_buy_clips_to_cash():
    p = Portfolio.fresh(500.0)
    ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
    bought = p.execute_buy("SPY", Decimal("100"), Decimal("100.00"), ts)
    # Can only buy 5 shares at $100
    assert bought == Decimal("5")
    assert float(p.cash) == pytest.approx(0.0, abs=1)


def test_portfolio_sell_increases_cash():
    p = Portfolio.fresh(10_000.0)
    ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
    p.execute_buy("SPY", Decimal("10"), Decimal("100.00"), ts)
    p.execute_sell("SPY", Decimal("10"), Decimal("110.00"), ts)
    assert "SPY" not in p.positions
    assert float(p.cash) == pytest.approx(10_000.0 - 1_000.0 + 1_100.0)


def test_portfolio_avg_entry_price_weighted():
    p = Portfolio.fresh(100_000.0)
    ts = datetime(2024, 1, 2, tzinfo=timezone.utc)
    p.execute_buy("SPY", Decimal("10"), Decimal("100.00"), ts)
    p.execute_buy("SPY", Decimal("10"), Decimal("200.00"), ts)
    avg = float(p.avg_entry_prices["SPY"])
    assert avg == pytest.approx(150.0)


# ─── Walk-forward tests ───────────────────────────────────────────────────────

def test_walk_forward_holdout_not_in_folds():
    """Walk-forward folds must not overlap with the holdout period."""
    dates = pd.date_range("2018-01-01", periods=500, freq="B")
    splitter = WalkForwardSplitter(n_folds=4, holdout_frac=0.2)
    folds, holdout_start, holdout_end = splitter.split(dates)

    assert folds, "Expected at least one fold"
    for fold in folds:
        assert fold.test_end < holdout_start, (
            f"Fold {fold.fold} test end {fold.test_end} overlaps holdout start {holdout_start}"
        )


def test_walk_forward_folds_are_ordered():
    dates = pd.date_range("2018-01-01", periods=500, freq="B")
    splitter = WalkForwardSplitter(n_folds=4, holdout_frac=0.2)
    folds, _, _ = splitter.split(dates)

    for i in range(1, len(folds)):
        assert folds[i].test_start > folds[i - 1].test_start


def test_walk_forward_expanding_train():
    """Expanding window: each fold's train starts at the same date."""
    dates = pd.date_range("2018-01-01", periods=500, freq="B")
    splitter = WalkForwardSplitter(n_folds=4, holdout_frac=0.2)
    folds, _, _ = splitter.split(dates)

    first_train_start = folds[0].train_start
    for fold in folds:
        assert fold.train_start == first_train_start
