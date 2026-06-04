"""APScheduler wrapper for the live trading loop.

Runs ``run_trading_cycle`` on a fixed interval during market hours.
The cycle itself checks the clock and skips gracefully when the market is closed,
so it's safe to run the scheduler 24/7.
"""

from __future__ import annotations

import signal
import sys

from apscheduler.schedulers.blocking import BlockingScheduler

from algotrader.broker.base import Broker
from algotrader.config import Settings
from algotrader.data.client import MarketDataClient
from algotrader.logging_config import get_logger
from algotrader.orchestration.live_loop import run_trading_cycle
from algotrader.reporting.storage import TradeStorage
from algotrader.risk.manager import RiskManager
from algotrader.strategy.base import Strategy

log = get_logger("scheduler")


def start_scheduler(
    broker: Broker,
    data_client: MarketDataClient,
    strategy: Strategy,
    risk_manager: RiskManager,
    storage: TradeStorage,
    settings: Settings,
    dry_run: bool = False,
) -> None:
    """Start the blocking scheduler. Runs until Ctrl-C."""
    scheduler = BlockingScheduler(timezone="America/New_York")

    def _cycle() -> None:
        try:
            run_trading_cycle(
                broker=broker,
                data_client=data_client,
                strategy=strategy,
                risk_manager=risk_manager,
                storage=storage,
                settings=settings,
                dry_run=dry_run,
            )
        except Exception as exc:
            log.error("cycle_error", error=str(exc), exc_info=True)

    scheduler.add_job(
        _cycle,
        trigger="interval",
        minutes=settings.schedule_interval_minutes,
        max_instances=1,
        id="trading_cycle",
    )

    def _shutdown(signum, frame) -> None:
        log.info("shutdown_requested")
        scheduler.shutdown(wait=False)
        sys.exit(0)

    signal.signal(signal.SIGINT, _shutdown)
    signal.signal(signal.SIGTERM, _shutdown)

    log.info(
        "scheduler_started",
        strategy=strategy.name,
        interval_minutes=settings.schedule_interval_minutes,
        dry_run=dry_run,
    )
    # Run immediately on startup, then on schedule.
    _cycle()
    scheduler.start()
