#!/usr/bin/env python3
"""Phase 4 deliverable — run the live paper-trading loop.

Starts the APScheduler loop that fires every N minutes. On each tick:
  1. Checks the market clock (skips if closed).
  2. Refreshes data from Alpaca.
  3. Generates strategy signals.
  4. Applies risk rules.
  5. Reconciles and submits paper orders.
  6. Logs and persists equity snapshot.

PAPER MONEY ONLY. AlpacaPaperBroker hardwires paper=True with no switch.

Usage:
    python -m scripts.run_live
    python -m scripts.run_live --strategy sma_crossover
    python -m scripts.run_live --dry-run       # log what WOULD be ordered; no orders
"""

from __future__ import annotations

import argparse
import sys

from algotrader.broker.alpaca_paper import AlpacaPaperBroker
from algotrader.config import load_settings
from algotrader.data.cache import BarCache
from algotrader.data.client import MarketDataClient
from algotrader.logging_config import configure_logging, get_logger
from algotrader.orchestration.scheduler import start_scheduler
from algotrader.reporting.storage import TradeStorage
from algotrader.risk.manager import RiskManager
from algotrader.strategy.buy_and_hold import BuyAndHold
from algotrader.strategy.sma_crossover import SmaCrossover


def main() -> None:
    parser = argparse.ArgumentParser(description="Live paper-trading loop")
    parser.add_argument("--strategy", choices=["sma_crossover", "buy_and_hold", "llm"],
                        help="Override strategy (default from .env)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute signals but do not place any orders")
    args = parser.parse_args()

    settings = load_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("run_live")

    name = args.strategy or settings.strategy_name
    if name == "buy_and_hold":
        strategy = BuyAndHold()
    elif name == "llm":
        from algotrader.strategy.llm_strategy import LlmStrategy
        if not settings.anthropic_api_key:
            print("ERROR: ANTHROPIC_API_KEY required for LLM strategy.", file=sys.stderr)
            sys.exit(1)
        strategy = LlmStrategy(
            api_key=settings.anthropic_api_key,
            symbols=settings.symbols,
            lookback_bars=settings.llm_lookback_bars,
            model=settings.llm_model,
            cache_dir=settings.llm_cache_dir,
        )
    else:
        strategy = SmaCrossover(settings.sma_fast_window, settings.sma_slow_window)

    broker = AlpacaPaperBroker(settings.alpaca_api_key, settings.alpaca_secret_key)
    cache  = BarCache(settings.data_dir)
    data   = MarketDataClient(settings.alpaca_api_key, settings.alpaca_secret_key, cache)
    risk   = RiskManager(settings.max_position_pct, settings.max_portfolio_drawdown_pct,
                         settings.stop_loss_pct)
    store  = TradeStorage(settings.data_dir)
    store.new_run(strategy.name, settings.symbols, settings.timeframe, run_type="live")

    log.info("live_start", strategy=strategy.name, symbols=settings.symbols,
             interval_minutes=settings.schedule_interval_minutes, dry_run=args.dry_run)

    if args.dry_run:
        log.info("dry_run_note", msg="No orders will be submitted.")

    start_scheduler(broker, data, strategy, risk, store, settings, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
