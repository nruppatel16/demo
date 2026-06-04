"""Risk management rules, applied uniformly to backtest AND live paths.

Three rules (all configurable, all independently disable-able):
  1. Position cap: no single position may exceed ``max_position_pct`` of equity.
  2. Drawdown kill-switch: if portfolio drawdown >= ``max_drawdown_pct``,
     go flat and stay flat for the remainder of the simulation/session.
  3. Per-position stop-loss: if a position's unrealized loss >= ``stop_loss_pct``,
     set its target weight to 0 (exit).

The manager is stateful (tracks peak equity for the kill-switch). Create a fresh
instance for each backtest run / live session.
"""

from __future__ import annotations

from decimal import Decimal


class RiskManager:
    def __init__(
        self,
        max_position_pct: float = 0.25,
        max_portfolio_drawdown_pct: float = 0.20,
        stop_loss_pct: float | None = None,
    ) -> None:
        self.max_position_pct = max_position_pct
        self.max_portfolio_drawdown_pct = max_portfolio_drawdown_pct
        self.stop_loss_pct = stop_loss_pct

        self._peak_equity: float | None = None
        self._killed = False

    @property
    def killed(self) -> bool:
        """True when the drawdown kill-switch has fired."""
        return self._killed

    def apply(
        self,
        raw_signals: dict[str, float],
        portfolio: object,        # algotrader.backtest.portfolio.Portfolio
        current_prices: dict[str, float],
    ) -> dict[str, float]:
        """Apply all risk rules. Returns final target weights [0.0, max_position_pct]."""
        from algotrader.backtest.portfolio import Portfolio
        assert isinstance(portfolio, Portfolio)

        equity = float(portfolio.equity(current_prices))

        # --- Update peak equity ---
        if self._peak_equity is None or equity > self._peak_equity:
            self._peak_equity = equity

        # --- Kill-switch check ---
        if self._peak_equity and self._peak_equity > 0:
            drawdown = 1.0 - equity / self._peak_equity
            if drawdown >= self.max_portfolio_drawdown_pct:
                self._killed = True

        if self._killed:
            return {sym: 0.0 for sym in raw_signals}

        # --- Cap individual positions ---
        result: dict[str, float] = {}
        for sym, weight in raw_signals.items():
            result[sym] = min(max(weight, 0.0), self.max_position_pct)

        # --- Per-position stop-loss ---
        if self.stop_loss_pct is not None:
            for sym in list(result.keys()):
                held = portfolio.positions.get(sym, Decimal(0))
                if held > 0:
                    avg_entry = portfolio.avg_entry_prices.get(sym)
                    price = current_prices.get(sym, 0.0)
                    if avg_entry and float(avg_entry) > 0 and price > 0:
                        loss = 1.0 - price / float(avg_entry)
                        if loss >= self.stop_loss_pct:
                            result[sym] = 0.0  # trigger stop: exit position

        return result

    def reset(self) -> None:
        """Reset state (call between independent backtest runs)."""
        self._peak_equity = None
        self._killed = False
