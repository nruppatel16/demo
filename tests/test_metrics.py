"""Metrics calculator tests (known analytic values)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from algotrader.metrics.calculator import compute_metrics, format_metrics_table


def _equity(values: list[float], start: str = "2020-01-01") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq="B")
    return pd.Series(values, index=idx, name="equity")


def test_flat_equity_zero_return():
    eq = _equity([100_000.0] * 252)
    m = compute_metrics(eq)
    assert m["total_return"] == pytest.approx(0.0, abs=1e-9)
    assert m["cagr"] == pytest.approx(0.0, abs=1e-9)
    assert m["volatility"] == pytest.approx(0.0, abs=1e-9)
    assert m["max_drawdown"] == pytest.approx(0.0, abs=1e-9)


def test_linear_growth_positive_return():
    closes = [100_000 + i * 100 for i in range(252)]
    eq = _equity(closes)
    m = compute_metrics(eq)
    assert m["total_return"] > 0
    assert m["cagr"] > 0


def test_drawdown_correct_for_simple_series():
    # Peak at 120, falls to 60: drawdown = -50%
    eq = _equity([100.0, 120.0, 90.0, 60.0, 80.0])
    m = compute_metrics(eq)
    assert m["max_drawdown"] == pytest.approx(-0.50, rel=0.01)


def test_sharpe_positive_when_returns_positive():
    closes = [100_000 * (1.001 ** i) for i in range(252)]
    eq = _equity(closes)
    m = compute_metrics(eq)
    assert m["sharpe"] > 0


def test_win_rate_all_up():
    closes = [100_000 * (1.01 ** i) for i in range(50)]
    eq = _equity(closes)
    m = compute_metrics(eq)
    assert m["win_rate"] == pytest.approx(1.0, abs=1e-6)


def test_win_rate_all_down():
    closes = [100_000 * (0.99 ** i) for i in range(50)]
    eq = _equity(closes)
    m = compute_metrics(eq)
    assert m["win_rate"] == pytest.approx(0.0, abs=1e-6)


def test_information_ratio_computed_when_benchmark_given():
    eq = _equity([100_000 * (1.001 ** i) for i in range(100)])
    bm = _equity([100_000 * (1.0005 ** i) for i in range(100)])
    m = compute_metrics(eq, bm)
    assert "information_ratio" in m


def test_too_short_returns_empty():
    eq = _equity([100_000.0])
    m = compute_metrics(eq)
    assert m == {}


def test_format_table_returns_string():
    m1 = {"total_return": 0.12, "cagr": 0.10, "sharpe": 0.9,
           "sortino": 1.1, "max_drawdown": -0.15, "volatility": 0.12, "win_rate": 0.53}
    m2 = {"total_return": 0.20, "cagr": 0.18, "sharpe": 1.1,
           "sortino": 1.5, "max_drawdown": -0.22, "volatility": 0.14, "win_rate": 0.55}
    table = format_metrics_table(m1, m2)
    assert "Total Return" in table
    assert "Sharpe" in table
    assert "Max Drawdown" in table
