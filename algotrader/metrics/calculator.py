"""Performance metrics calculator.

All metrics are annualized using 252 trading days/year.
Every strategy is always compared to the buy-and-hold benchmark.
Results are reported honestly — including when the strategy underperforms.

Metrics computed:
  total_return    - cumulative return over the full period
  cagr            - compound annual growth rate
  sharpe          - annualized Sharpe ratio (risk-free rate = 0, conservative)
  sortino         - annualized Sortino ratio (downside deviation only)
  max_drawdown    - worst peak-to-trough decline (negative number)
  volatility      - annualized daily return std dev
  win_rate        - fraction of trading days with positive return
  turnover        - annualized portfolio turnover (from trade list)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS_PER_YEAR = 252


def compute_metrics(
    equity: pd.Series,
    benchmark: pd.Series | None = None,
) -> dict[str, float]:
    """Compute all metrics for ``equity`` curve.

    Args:
        equity: DatetimeIndex -> float equity values (e.g. starting at 100_000).
        benchmark: optional benchmark equity curve for excess-return context.
    """
    if len(equity) < 2:
        return {}

    equity = equity.sort_index().astype(float)
    returns = equity.pct_change().dropna()

    n_years = max(len(returns) / TRADING_DAYS_PER_YEAR, 1 / TRADING_DAYS_PER_YEAR)

    total_return = float(equity.iloc[-1] / equity.iloc[0] - 1)
    cagr = float((1 + total_return) ** (1.0 / n_years) - 1)

    vol = float(returns.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
    mean_return_annual = float(returns.mean() * TRADING_DAYS_PER_YEAR)

    sharpe = mean_return_annual / vol if vol > 0 else 0.0

    downside = returns[returns < 0]
    downside_vol = float(downside.std() * np.sqrt(TRADING_DAYS_PER_YEAR)) if len(downside) > 0 else 0.0
    sortino = mean_return_annual / downside_vol if downside_vol > 0 else 0.0

    rolling_max = equity.expanding().max()
    drawdown = (equity - rolling_max) / rolling_max
    max_drawdown = float(drawdown.min())

    win_rate = float((returns > 0).sum() / len(returns))

    result = {
        "total_return": total_return,
        "cagr": cagr,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_drawdown": max_drawdown,
        "volatility": vol,
        "win_rate": win_rate,
    }

    if benchmark is not None and len(benchmark) >= 2:
        bench_returns = benchmark.pct_change().dropna()
        aligned = returns.align(bench_returns, join="inner")
        excess = aligned[0] - aligned[1]
        tracking_vol = float(excess.std() * np.sqrt(TRADING_DAYS_PER_YEAR))
        info_ratio = (float(excess.mean() * TRADING_DAYS_PER_YEAR) / tracking_vol
                      if tracking_vol > 0 else 0.0)
        result["information_ratio"] = info_ratio

    return result


def format_metrics_table(
    strategy_metrics: dict[str, float],
    benchmark_metrics: dict[str, float],
    strategy_name: str = "Strategy",
    benchmark_name: str = "BuyAndHold",
) -> str:
    """Return a human-readable two-column metrics table."""
    rows = [
        ("Total Return",  "total_return",  "{:+.1%}"),
        ("CAGR",          "cagr",          "{:+.1%}"),
        ("Sharpe",        "sharpe",        "{:.2f}"),
        ("Sortino",       "sortino",       "{:.2f}"),
        ("Max Drawdown",  "max_drawdown",  "{:.1%}"),
        ("Volatility",    "volatility",    "{:.1%}"),
        ("Win Rate",      "win_rate",      "{:.1%}"),
        ("Info Ratio",    "information_ratio", "{:.2f}"),
    ]

    col = 20
    header = f"{'Metric':<{col}}  {strategy_name:>14}  {benchmark_name:>14}"
    sep = "-" * len(header)
    lines = [sep, header, sep]

    for label, key, fmt in rows:
        s_val = strategy_metrics.get(key)
        b_val = benchmark_metrics.get(key)
        s_str = fmt.format(s_val) if s_val is not None else "n/a"
        b_str = fmt.format(b_val) if b_val is not None else "n/a"
        lines.append(f"{label:<{col}}  {s_str:>14}  {b_str:>14}")

    lines.append(sep)
    return "\n".join(lines)
