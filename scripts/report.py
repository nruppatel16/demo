#!/usr/bin/env python3
"""Phase 5 deliverable — CLI performance report from stored results.

Reads trade history and metrics from the DuckDB results store and prints
a formatted summary. Optionally re-generates the equity-curve plot.

Usage:
    python -m scripts.report                     # show last 5 runs
    python -m scripts.report --run-id <id>       # show a specific run
    python -m scripts.report --latest 10         # show last N runs
    python -m scripts.report --run-id <id> --plot  # re-generate equity chart
"""

from __future__ import annotations

import argparse

from algotrader.config import load_settings
from algotrader.logging_config import configure_logging
from algotrader.reporting.storage import TradeStorage


def main() -> None:
    parser = argparse.ArgumentParser(description="Performance report CLI")
    parser.add_argument("--run-id", help="Show a specific run by ID")
    parser.add_argument("--latest", type=int, default=5,
                        help="Number of recent runs to list (default: 5)")
    parser.add_argument("--plot", action="store_true",
                        help="Re-generate equity-curve PNG for the selected run")
    args = parser.parse_args()

    settings = load_settings()
    configure_logging(settings.log_level, settings.log_json)
    store = TradeStorage(settings.data_dir)

    # --- List recent runs ---
    runs_df = store.list_runs(n=args.latest)
    if runs_df.empty:
        print("No runs found in store. Run `python -m scripts.backtest_run --save` first.")
        return

    print(f"\n{'='*70}")
    print(f"  Recent Runs (last {args.latest})")
    print(f"{'='*70}")
    print(runs_df.to_string(index=False))
    print()

    run_id = args.run_id or runs_df.iloc[0]["run_id"]
    print(f"{'='*70}")
    print(f"  Run: {run_id}")
    print(f"{'='*70}")

    # --- Metrics table ---
    metrics_df = store.get_metrics(run_id)
    if metrics_df.empty:
        print("  No metrics stored for this run.")
    else:
        pivot = metrics_df.pivot(index="metric_name", columns="strategy_name",
                                  values="metric_value")
        print("\n  Performance Metrics:")
        print(pivot.to_string())

    # --- Trade summary ---
    trades_df = store.get_trades(run_id)
    print(f"\n  Trades: {len(trades_df)} total")
    if not trades_df.empty:
        print(trades_df[["ts", "strategy_name", "symbol", "side", "shares", "fill_price"]]
              .tail(10).to_string(index=False))
        print("  (showing last 10 trades)")

    # --- Plot ---
    if args.plot:
        import pandas as pd
        import matplotlib
        matplotlib.use("Agg")

        strategies = metrics_df["strategy_name"].unique() if not metrics_df.empty else []
        eq_map = {}
        for strat in strategies:
            eq_df = store.get_equity_curve(run_id, strat)
            if not eq_df.empty:
                eq_map[strat] = pd.Series(
                    eq_df["equity"].values,
                    index=pd.DatetimeIndex(eq_df["ts"])
                )

        if len(eq_map) >= 2:
            import matplotlib.pyplot as plt
            import os
            fig, ax = plt.subplots(figsize=(12, 5))
            for strat, eq in eq_map.items():
                normalized = eq / eq.iloc[0]
                ax.plot(normalized.index, normalized.values, label=strat)
            ax.set_title(f"Equity Curve — run {run_id[:8]}")
            ax.set_ylabel("Normalized Equity")
            ax.legend()
            ax.grid(alpha=0.3)
            os.makedirs("reports", exist_ok=True)
            path = f"reports/run_{run_id[:8]}.png"
            plt.savefig(path, dpi=150, bbox_inches="tight")
            plt.close(fig)
            print(f"\n  Equity curve saved: {path}")


if __name__ == "__main__":
    main()
