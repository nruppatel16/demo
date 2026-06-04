"""CLI performance reporter + equity-curve plotter.

``print_report`` reads a completed BacktestResult and writes a structured
summary to stdout. ``save_equity_plot`` saves a two-panel PNG (equity + drawdown).
``persist_result`` writes everything to TradeStorage.
"""

from __future__ import annotations

import os

import pandas as pd

from algotrader.backtest.engine import BacktestResult
from algotrader.metrics.calculator import format_metrics_table


def print_report(result: BacktestResult) -> None:
    """Print a complete, honest performance summary to stdout."""
    print()
    print("=" * 62)
    print(f"  Backtest: {result.strategy_name}  vs  BuyAndHold")
    print(f"  Symbols : {', '.join(result.symbols)}")
    print(f"  Period  : {result.start_date.date()} → {result.end_date.date()}")
    print("=" * 62)

    table = format_metrics_table(
        result.metrics,
        result.benchmark_metrics,
        strategy_name=result.strategy_name,
        benchmark_name="BuyAndHold",
    )
    print(table)

    print(f"\n  Trades executed : {len(result.trades)}")
    buys  = sum(1 for t in result.trades if t.side == "buy")
    sells = sum(1 for t in result.trades if t.side == "sell")
    print(f"    Buys  : {buys}")
    print(f"    Sells : {sells}")
    print()
    print("  Survivorship-bias note: results reflect a hand-picked symbol")
    print("  universe. Past performance does not predict future results.")
    print()


def save_equity_plot(
    result: BacktestResult,
    output_dir: str = "reports",
    filename: str | None = None,
) -> str:
    """Save a two-panel equity + drawdown chart. Returns the file path."""
    import matplotlib
    matplotlib.use("Agg")   # non-interactive; no display required
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    import numpy as np

    os.makedirs(output_dir, exist_ok=True)
    if filename is None:
        ts = result.start_date.strftime("%Y%m%d")
        filename = f"{result.strategy_name}_vs_bah_{ts}.png"
    path = os.path.join(output_dir, filename)

    eq = result.equity_curve / result.equity_curve.iloc[0]
    bm = result.benchmark_equity / result.benchmark_equity.iloc[0]

    rolling_max_eq = eq.expanding().max()
    dd_eq = (eq - rolling_max_eq) / rolling_max_eq
    rolling_max_bm = bm.expanding().max()
    dd_bm = (bm - rolling_max_bm) / rolling_max_bm

    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 7), sharex=True,
                                    gridspec_kw={"height_ratios": [3, 1]})
    fig.suptitle(
        f"{result.strategy_name} vs BuyAndHold  |  "
        f"{result.start_date.date()} – {result.end_date.date()}",
        fontsize=12, fontweight="bold",
    )

    ax1.plot(eq.index, eq.values, label=result.strategy_name, linewidth=1.5, color="#2563eb")
    ax1.plot(bm.index, bm.values, label="BuyAndHold", linewidth=1.5, color="#9ca3af", linestyle="--")
    ax1.axhline(1.0, color="#374151", linewidth=0.5, linestyle=":")
    ax1.set_ylabel("Normalized Equity (start = 1.0)")
    ax1.legend(loc="upper left")
    ax1.grid(True, alpha=0.3)

    ax2.fill_between(dd_eq.index, dd_eq.values, 0, alpha=0.5, color="#2563eb", label=result.strategy_name)
    ax2.fill_between(dd_bm.index, dd_bm.values, 0, alpha=0.3, color="#9ca3af", label="BuyAndHold")
    ax2.set_ylabel("Drawdown")
    ax2.set_xlabel("Date")
    ax2.yaxis.set_major_formatter(plt.FuncFormatter(lambda x, _: f"{x:.0%}"))
    ax2.grid(True, alpha=0.3)
    ax2.legend(loc="lower left", fontsize=8)

    ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m"))
    plt.xticks(rotation=30)

    plt.tight_layout()
    plt.savefig(path, dpi=150, bbox_inches="tight")
    plt.close(fig)
    return path


def persist_result(
    result: BacktestResult,
    storage: object,                  # TradeStorage
    result_type: str = "backtest",
) -> str:
    """Write a BacktestResult to TradeStorage. Returns the run_id."""
    from algotrader.reporting.storage import TradeStorage
    assert isinstance(storage, TradeStorage)

    run_id = storage.new_run(
        strategy_name=result.strategy_name,
        symbols=result.symbols,
        timeframe="1Day",
        run_type=result_type,
        start_date=result.start_date,
        end_date=result.end_date,
    )
    storage.record_trades(result.trades, result.strategy_name, run_id)
    storage.record_equity_series(result.equity_curve, result.strategy_name, run_id)
    storage.record_equity_series(result.benchmark_equity, "buy_and_hold", run_id)
    storage.record_metrics(result.metrics, result.strategy_name, run_id)
    storage.record_metrics(result.benchmark_metrics, "buy_and_hold", run_id)
    return run_id
