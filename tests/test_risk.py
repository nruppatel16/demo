"""Risk manager unit tests."""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from algotrader.backtest.portfolio import Portfolio
from algotrader.risk.manager import RiskManager


def _portfolio(cash=100_000.0, positions=None, avg_entry=None) -> Portfolio:
    p = Portfolio.fresh(cash)
    if positions:
        p.positions = {sym: Decimal(str(qty)) for sym, qty in positions.items()}
    if avg_entry:
        p.avg_entry_prices = {sym: Decimal(str(px)) for sym, px in avg_entry.items()}
    return p


PRICES = {"SPY": 450.0, "QQQ": 380.0}


def test_position_cap_reduces_overweight():
    rm = RiskManager(max_position_pct=0.25)
    signals = {"SPY": 1.0}
    result = rm.apply(signals, _portfolio(), PRICES)
    assert result["SPY"] == pytest.approx(0.25)


def test_position_cap_does_not_reduce_underweight():
    rm = RiskManager(max_position_pct=0.25)
    signals = {"SPY": 0.10}
    result = rm.apply(signals, _portfolio(), PRICES)
    assert result["SPY"] == pytest.approx(0.10)


def test_negative_weight_clamped_to_zero():
    rm = RiskManager(max_position_pct=1.0)
    signals = {"SPY": -0.5}
    result = rm.apply(signals, _portfolio(), PRICES)
    assert result["SPY"] == 0.0


def test_kill_switch_activates_on_drawdown():
    rm = RiskManager(max_portfolio_drawdown_pct=0.20)
    # Establish a peak
    peak_portfolio = _portfolio(cash=100_000.0)
    rm.apply({"SPY": 0.5}, peak_portfolio, {"SPY": 100.0})

    # Now simulate 25% loss
    loss_portfolio = _portfolio(cash=75_000.0)
    result = rm.apply({"SPY": 1.0}, loss_portfolio, {"SPY": 100.0})
    assert rm.killed is True
    assert result == {"SPY": 0.0}


def test_kill_switch_stays_off_below_threshold():
    rm = RiskManager(max_portfolio_drawdown_pct=0.20)
    peak_portfolio = _portfolio(cash=100_000.0)
    rm.apply({"SPY": 0.0}, peak_portfolio, {"SPY": 100.0})

    # Only 10% loss — below the 20% threshold
    slight_loss = _portfolio(cash=90_000.0)
    result = rm.apply({"SPY": 0.5}, slight_loss, {"SPY": 100.0})
    assert rm.killed is False
    assert result["SPY"] > 0


def test_kill_switch_stays_engaged():
    """Once the kill switch fires, it stays on even if equity recovers."""
    rm = RiskManager(max_portfolio_drawdown_pct=0.10)
    rm.apply({"SPY": 0.0}, _portfolio(100_000.0), {"SPY": 100.0})
    rm.apply({"SPY": 0.0}, _portfolio(85_000.0), {"SPY": 100.0})
    assert rm.killed

    # "Recovery" — equity back up
    result = rm.apply({"SPY": 1.0}, _portfolio(120_000.0), {"SPY": 100.0})
    assert rm.killed is True
    assert result == {"SPY": 0.0}


def test_stop_loss_exits_position():
    rm = RiskManager(max_position_pct=1.0, stop_loss_pct=0.10)
    # Position bought at 100; now at 85 → 15% loss → triggers stop
    port = _portfolio(
        cash=50_000.0,
        positions={"SPY": 50},
        avg_entry={"SPY": 100.0},
    )
    result = rm.apply({"SPY": 1.0}, port, {"SPY": 85.0})
    assert result["SPY"] == 0.0


def test_stop_loss_does_not_trigger_within_threshold():
    rm = RiskManager(max_position_pct=1.0, stop_loss_pct=0.10)
    port = _portfolio(
        cash=50_000.0,
        positions={"SPY": 50},
        avg_entry={"SPY": 100.0},
    )
    # Only 5% loss — below 10% threshold
    result = rm.apply({"SPY": 1.0}, port, {"SPY": 95.0})
    assert result["SPY"] > 0.0


def test_risk_reset_clears_kill_switch():
    rm = RiskManager(max_portfolio_drawdown_pct=0.05)
    rm.apply({"SPY": 0.0}, _portfolio(100_000.0), {"SPY": 100.0})
    rm.apply({"SPY": 0.0}, _portfolio(90_000.0),  {"SPY": 100.0})
    assert rm.killed

    rm.reset()
    assert rm.killed is False
    result = rm.apply({"SPY": 0.5}, _portfolio(90_000.0), {"SPY": 100.0})
    assert result["SPY"] > 0
