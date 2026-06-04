#!/usr/bin/env python3
"""Phase 1 connectivity smoke test.

Proves end-to-end wiring against your Alpaca PAPER account:
  1. Authenticates and prints account info.
  2. Fetches recent daily bars for the first configured symbol.
  3. Reports the market clock.
  4. (Unless --dry-run) places ONE tiny paper order, then cancels it; if it had
     already filled (market open), liquidates the resulting position so the
     account is left flat.

Requires a populated `.env` (see `.env.example`). Paper money only.

Usage:
    python -m scripts.smoke_test            # full run (places + unwinds 1 order)
    python -m scripts.smoke_test --dry-run  # skip order placement
    python -m scripts.smoke_test --qty 1    # order size in shares (default 1)
"""

from __future__ import annotations

import argparse
import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from algotrader.broker.alpaca_paper import AlpacaPaperBroker
from algotrader.broker.models import OrderRequest, OrderSide
from algotrader.config import load_settings
from algotrader.data.cache import BarCache
from algotrader.data.client import MarketDataClient
from algotrader.logging_config import configure_logging, get_logger


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 1 connectivity smoke test")
    parser.add_argument(
        "--dry-run", action="store_true", help="skip placing/canceling any order"
    )
    parser.add_argument(
        "--qty", type=int, default=1, help="order size in shares (default: 1)"
    )
    args = parser.parse_args()

    settings = load_settings()
    configure_logging(settings.log_level, settings.log_json)
    log = get_logger("smoke_test")

    symbol = settings.symbols[0]
    broker = AlpacaPaperBroker(settings.alpaca_api_key, settings.alpaca_secret_key)
    data = MarketDataClient(
        settings.alpaca_api_key,
        settings.alpaca_secret_key,
        cache=BarCache(settings.data_dir),
    )

    # 1. Account ----------------------------------------------------------------
    account = broker.get_account()
    log.info(
        "account",
        cash=str(account.cash),
        equity=str(account.equity),
        buying_power=str(account.buying_power),
        currency=account.currency,
    )

    # 2. Recent bars ------------------------------------------------------------
    end = datetime.now(timezone.utc) - timedelta(minutes=20)  # avoid SIP delay
    start = end - timedelta(days=10)
    bars = data.get_bars(symbol, settings.timeframe, start, end)
    log.info("bars_fetched", symbol=symbol, rows=len(bars))
    if not bars.empty:
        last = bars.iloc[-1]
        log.info(
            "latest_bar",
            symbol=symbol,
            ts=str(bars.index[-1]),
            close=float(last["close"]),
        )

    # 3. Clock ------------------------------------------------------------------
    clock = broker.get_clock()
    log.info(
        "clock",
        is_open=clock.is_open,
        next_open=str(clock.next_open),
        next_close=str(clock.next_close),
    )

    # 4. One tiny round-trip paper order ---------------------------------------
    if args.dry_run:
        log.info("dry_run", note="skipping order placement")
        return

    order = broker.submit_order(
        OrderRequest(symbol=symbol, qty=Decimal(args.qty), side=OrderSide.BUY)
    )
    log.info("order_submitted", id=order.id, symbol=order.symbol, status=order.status)

    time.sleep(2)  # give the paper engine a moment

    try:
        broker.cancel_order(order.id)
        log.info("order_canceled", id=order.id)
    except Exception as exc:  # noqa: BLE001 - smoke test is intentionally tolerant
        log.warning("cancel_failed_checking_fill", id=order.id, error=str(exc))

    # If the order filled before we could cancel (market open), unwind it.
    position = broker.get_position(symbol)
    if position is not None:
        closing = broker.close_position(symbol)
        log.info(
            "position_closed",
            symbol=symbol,
            qty=str(position.qty),
            closing_order_id=closing.id,
        )

    log.info("smoke_test_complete", status="ok")


if __name__ == "__main__":
    main()
