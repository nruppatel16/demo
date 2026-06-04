"""Live paper-trading loop.

One call to ``run_trading_cycle`` performs a complete decision cycle:
  1. Check market clock — skip gracefully if closed.
  2. Hydrate portfolio from broker state.
  3. Fetch recent bars (enough for the strategy's lookback).
  4. Generate strategy signals.
  5. Apply risk rules.
  6. Reconcile target vs. current positions.
  7. Submit paper orders.
  8. Log everything; persist equity snapshot.

The same ``Strategy`` and ``RiskManager`` objects used in backtesting run here,
so paper results reflect the tested logic.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from algotrader.backtest.portfolio import Portfolio
from algotrader.broker.base import Broker
from algotrader.broker.models import OrderRequest, OrderSide
from algotrader.config import Settings
from algotrader.data.client import MarketDataClient
from algotrader.logging_config import get_logger
from algotrader.reporting.storage import TradeStorage
from algotrader.risk.manager import RiskManager
from algotrader.strategy.base import Strategy

log = get_logger("live_loop")


def run_trading_cycle(
    broker: Broker,
    data_client: MarketDataClient,
    strategy: Strategy,
    risk_manager: RiskManager,
    storage: TradeStorage,
    settings: Settings,
    dry_run: bool = False,
) -> None:
    """Execute one full trading cycle. Safe to call on any schedule."""
    clock = broker.get_clock()
    if not clock.is_open:
        log.info("market_closed", next_open=str(clock.next_open))
        return

    # --- Hydrate portfolio from broker ---
    account = broker.get_account()
    positions = broker.get_positions()
    portfolio = Portfolio.from_broker(account, positions)

    # --- Fetch data (generous lookback; cache handles redundant fetches) ---
    lookback_days = max(settings.sma_slow_window * 3, 90)
    end = datetime.now(timezone.utc) - timedelta(minutes=20)   # respect SIP 15-min delay
    start = end - timedelta(days=lookback_days)

    bars: dict = {}
    for sym in settings.symbols:
        df = data_client.get_bars(sym, settings.timeframe, start, end)
        if not df.empty:
            bars[sym] = df

    if not bars:
        log.warning("no_data", symbols=settings.symbols)
        return

    # --- Generate signals (strategy sees only historical data, no future) ---
    raw_signals = strategy.generate_signals(bars)

    # --- Apply risk rules ---
    current_prices = {sym: float(df.iloc[-1]["close"]) for sym, df in bars.items()}
    target_weights = risk_manager.apply(raw_signals, portfolio, current_prices)

    # --- Compute target share counts ---
    target_shares = portfolio.target_shares(target_weights, current_prices)

    # --- Compute deltas and submit orders ---
    deltas = portfolio.order_deltas(target_shares, settings.symbols)
    orders_submitted = 0

    for sym, delta in deltas:
        side = OrderSide.BUY if delta > 0 else OrderSide.SELL
        qty = abs(delta)
        if dry_run:
            log.info("dry_run_order", symbol=sym, side=side.value, qty=str(qty))
            continue
        try:
            order = broker.submit_order(OrderRequest(symbol=sym, qty=qty, side=side))
            log.info("order_submitted", id=order.id, symbol=sym, side=side.value, qty=str(qty))
            storage.record_order(
                strategy_name=strategy.name,
                symbol=sym,
                side=side.value,
                shares=float(qty),
                order_id=order.id,
            )
            orders_submitted += 1
        except Exception as exc:
            log.error("order_failed", symbol=sym, side=side.value, qty=str(qty), error=str(exc))

    # --- Persist equity snapshot ---
    equity = float(portfolio.equity(current_prices))
    storage.record_equity_snapshot(strategy_name=strategy.name, equity=equity)

    log.info(
        "cycle_complete",
        strategy=strategy.name,
        equity=round(equity, 2),
        n_signals=len(raw_signals),
        n_orders=orders_submitted,
        kill_switch_active=risk_manager.killed,
    )
