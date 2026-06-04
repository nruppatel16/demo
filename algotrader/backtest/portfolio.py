"""Portfolio state, shared between the backtest engine and the live loop.

Tracks cash, share positions, average entry prices, and a trade log.
All money arithmetic uses Decimal to avoid float rounding error.

``from_broker`` reconstructs a Portfolio from live broker state so that the
live loop and the backtest engine work with the same type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, ROUND_FLOOR


@dataclass
class Trade:
    symbol: str
    side: str            # "buy" | "sell"
    shares: Decimal
    fill_price: Decimal
    timestamp: datetime
    slippage_bps: float = 0.0


@dataclass
class Portfolio:
    cash: Decimal
    positions: dict[str, Decimal] = field(default_factory=dict)
    avg_entry_prices: dict[str, Decimal] = field(default_factory=dict)
    trades: list[Trade] = field(default_factory=list)

    # --- Valuation ---

    def equity(self, prices: dict[str, float]) -> Decimal:
        """Cash + mark-to-market value of all open positions."""
        pos_value = sum(
            self.positions[sym] * Decimal(str(prices[sym]))
            for sym in self.positions
            if sym in prices and prices[sym] > 0
        )
        return self.cash + pos_value

    # --- Order execution ---

    def execute_buy(
        self, symbol: str, shares: Decimal, fill_price: Decimal,
        ts: datetime, slippage_bps: float = 0.0
    ) -> Decimal:
        """Buy ``shares`` at ``fill_price``. Clips to available cash. Returns actual shares bought."""
        if shares <= 0 or fill_price <= 0:
            return Decimal(0)
        cost = shares * fill_price
        if cost > self.cash:
            # Clip to what we can afford (whole shares only)
            shares = (self.cash / fill_price).to_integral_value(rounding=ROUND_FLOOR)
            cost = shares * fill_price
        if shares <= 0:
            return Decimal(0)

        current = self.positions.get(symbol, Decimal(0))
        current_avg = self.avg_entry_prices.get(symbol, Decimal(0))
        new_shares = current + shares
        # Weighted average entry price
        self.avg_entry_prices[symbol] = (current * current_avg + shares * fill_price) / new_shares

        self.cash -= cost
        self.positions[symbol] = new_shares
        self.trades.append(Trade(symbol, "buy", shares, fill_price, ts, slippage_bps))
        return shares

    def execute_sell(
        self, symbol: str, shares: Decimal, fill_price: Decimal,
        ts: datetime, slippage_bps: float = 0.0
    ) -> Decimal:
        """Sell up to ``shares`` at ``fill_price``. Clips to held shares. Returns shares sold."""
        if shares <= 0 or fill_price <= 0:
            return Decimal(0)
        held = self.positions.get(symbol, Decimal(0))
        shares = min(shares, held)
        if shares <= 0:
            return Decimal(0)

        self.cash += shares * fill_price
        remaining = held - shares
        if remaining <= 0:
            self.positions.pop(symbol, None)
            self.avg_entry_prices.pop(symbol, None)
        else:
            self.positions[symbol] = remaining

        self.trades.append(Trade(symbol, "sell", shares, fill_price, ts, slippage_bps))
        return shares

    # --- Convenience ---

    def target_shares(
        self, target_weights: dict[str, float], prices: dict[str, float]
    ) -> dict[str, Decimal]:
        """Convert target weights -> whole share counts based on current equity."""
        eq = float(self.equity(prices))
        result: dict[str, Decimal] = {}
        for sym, w in target_weights.items():
            price = prices.get(sym, 0.0)
            if price > 0 and w >= 0:
                dollar_target = eq * min(w, 1.0)
                shares = int(dollar_target / price)
                result[sym] = Decimal(shares)
        return result

    def order_deltas(
        self, target_shares: dict[str, Decimal], all_symbols: list[str]
    ) -> list[tuple[str, Decimal]]:
        """Return (symbol, delta) pairs to move from current to target.

        Positive delta = buy, negative = sell. Symbols with delta < 1 share
        are skipped (sub-share orders aren't modelled in v1).
        """
        deltas = []
        for sym in all_symbols:
            current = self.positions.get(sym, Decimal(0))
            target = target_shares.get(sym, Decimal(0))
            delta = target - current
            if abs(delta) >= 1:
                deltas.append((sym, delta))
        return deltas

    @classmethod
    def fresh(cls, initial_capital: float) -> "Portfolio":
        return cls(cash=Decimal(str(initial_capital)))

    @classmethod
    def from_broker(cls, account: object, positions: list[object]) -> "Portfolio":
        """Hydrate from live broker state (for the live loop)."""
        from algotrader.broker.models import Account, Position
        assert isinstance(account, Account)
        pos_map = {}
        avg_map = {}
        for p in positions:
            assert isinstance(p, Position)
            pos_map[p.symbol] = p.qty
            avg_map[p.symbol] = p.avg_entry_price
        return cls(cash=account.cash, positions=pos_map, avg_entry_prices=avg_map)
