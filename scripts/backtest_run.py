#!/usr/bin/env python3
"""Phase 3 deliverable — run a walk-forward backtest and print an honest report.

Fetches historical bars, runs walk-forward validation, then tests on the
out-of-sample holdout. SmaCrossover is always compared against BuyAndHold.
Results are reported for every fold + the final holdout. In-sample results
are explicitly labelled as such and not used for performance claims.

Usage:
    python -m scripts.backtest_run                              # uses .env settings
    python -m scripts.backtest_run --symbol SPY --start 2018-01-01 --end 2024-12-31
    python -m scripts.backtest_run --strategy sma_crossover --fast 10 --slow 30
    python -m scripts.backtest_run --strategy llm             # Phase 6 (needs ANTHROPIC_API_KEY)
    python -m scripts.backtest_run --save                     # persist to results.duckdb
    python -m scripts.backtest_run --plot                     # save equity-curve PNG
"""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone

from algotrader.backtest.engine import BacktestEngine
from algotrader.backtest.walk_forward import WalkForwardSplitter
from algotrader.config import load_settings
from algotrader.data.cache import BarCache
from algotrader.data.client import MarketDataClient
from algotrader.logging_config import configure_logging, get_logger
from algotrader.metrics.calculator import format_metrics_table
from algotrader.reporting.report import persist_result, print_report, save_equity_plot
from algotrader.reporting.storage import TradeStorage
from algotrader.risk.manager import RiskManager
from algotrader.strategy.buy_and_hold import BuyAndHold
from algotrader.strategy.sma_crossover import SmaCrossover


def build_strategy(args, settings):
    name = args.strategy or settings.strategy_name
    if name == "buy_and_hold":
        return BuyAndHold()
    if name == "llm":
        from algotrader.strategy.llm_strategy import LlmStrategy
        if not settings.anthropic_api_key:
            print("ERROR: ANTHROPIC_API_KEY must be set to use the LLM strategy.", file=sys.stderr)
            sys.exit(1)
        return LlmStrategy(
            api_key=settings.anthropic_api_key,
            symbols=settings.symbols,
            lookback_bars=settings.llm_lookback_bars,
            model=settings.llm_model,
            cache_dir=settings.llm_cache_dir,
        )
    fast = args.fast or settings.sma_fast_window
    slow = args.slow or settings.sma_slow_window
    return SmaCrossover(fast_window=fast, slow_window=slow)


def run_backtest_on_slice(bars, strategy, settings, start, end):
    """Run one backtest slice [start, end] with a fresh risk manager."""
    sliced = {sym: df.loc[start:end] for sym, df in bars.items()}
    risk = RiskManager(
        max_position_pct=settings.max_position_pct,
        max_portfolio_drawdown_pct=settings.max_portfolio_drawdown_pct,
        stop_loss_pct=settings.stop_loss_pct,
    )
    engine = BacktestEngine(
        bars=sliced,
        strategy=strategy,
        risk_manager=risk,
        initial_capital=settings.initial_capital,
        slippage_bps=settings.slippage_bps,
    )
    return engine.run()


def main() -> None:
    parser = argparse.ArgumentParser(description="Walk-forward backtest runner")
    parser.add_argument("--symbol", help="Override symbol (default from .env)")
    parser.add_argument("--start", default="2018-01-01", help="Data start date")
    parser.add_argument("--end",   default=None,         help="Data end date (default: today)")
    parser.add_argument("--strategy", choices=["sma_crossover", "buy_and_hold", "llm"])
    parser.add_argument("--fast", type=int)
    parser.add_argument("--slow", type=int)
    parser.add_argument("--save",  action="store_true", help="Persist results to DuckDB")
    parser.add_argument("--plot",  action="store_true", help="Save equity-curve PNG")
    args = parser.parse_args()

    settings = load_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("backtest_run")

    symbols = [args.symbol.upper()] if args.symbol else settings.symbols
    strategy = build_strategy(args, settings)
    end_str = args.end or datetime.now(timezone.utc).strftime("%Y-%m-%d")

    log.info("backtest_start", strategy=strategy.name, symbols=symbols,
             start=args.start, end=end_str)

    # --- Fetch data ---
    cache = BarCache(settings.data_dir)
    data_client = MarketDataClient(settings.alpaca_api_key, settings.alpaca_secret_key, cache)
    start_dt = datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc)
    end_dt   = datetime.fromisoformat(end_str).replace(tzinfo=timezone.utc)

    bars: dict = {}
    for sym in symbols:
        df = data_client.get_bars(sym, settings.timeframe, start_dt, end_dt)
        if df.empty:
            log.error("no_data", symbol=sym)
            sys.exit(1)
        bars[sym] = df
        log.info("data_loaded", symbol=sym, rows=len(df),
                 first=str(df.index[0])[:10], last=str(df.index[-1])[:10])

    # Common date index across all symbols
    from functools import reduce
    import pandas as pd
    common_idx = reduce(lambda a, b: a.intersection(b),
                        [df.index for df in bars.values()])
    common_idx = common_idx.sort_values()

    # --- Walk-forward splits ---
    splitter = WalkForwardSplitter(min_train_frac=0.5, n_folds=4, holdout_frac=0.2)
    folds, holdout_start, holdout_end = splitter.split(common_idx)

    print(f"\n{'='*62}")
    print(f"  Walk-Forward Out-of-Sample Results")
    print(f"  Strategy : {strategy.name}")
    print(f"  Symbols  : {', '.join(symbols)}")
    print(f"  Holdout  : {holdout_start.date()} → {holdout_end.date()} (NEVER seen during tuning)")
    print(f"{'='*62}")

    storage = TradeStorage(settings.data_dir) if args.save else None

    for fold in folds:
        result = run_backtest_on_slice(bars, strategy, settings,
                                       fold.test_start, fold.test_end)
        print(f"\n  Fold {fold.fold} out-of-sample: {fold.test_start.date()} → {fold.test_end.date()}")
        table = format_metrics_table(result.metrics, result.benchmark_metrics,
                                     strategy.name, "BuyAndHold")
        print(table)
        if storage:
            persist_result(result, storage)

    # --- Final holdout (never seen during any tuning) ---
    print(f"\n{'='*62}")
    print(f"  FINAL HOLDOUT (out-of-sample, never touched during tuning)")
    print(f"  {holdout_start.date()} → {holdout_end.date()}")
    print(f"{'='*62}")
    holdout_result = run_backtest_on_slice(bars, strategy, settings,
                                           holdout_start, holdout_end)
    print_report(holdout_result)

    if args.plot:
        plot_path = save_equity_plot(holdout_result)
        print(f"  Equity curve saved: {plot_path}")

    if storage:
        run_id = persist_result(holdout_result, storage, result_type="holdout")
        print(f"  Results saved (run_id={run_id})")


if __name__ == "__main__":
    main()
