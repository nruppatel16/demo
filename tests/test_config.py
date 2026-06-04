"""Config parsing tests (no env/.env dependency)."""

from __future__ import annotations

from algotrader.config import Settings


def _make(**overrides) -> Settings:
    base = dict(
        _env_file=None,  # do not read a real .env during tests
        alpaca_api_key="key",
        alpaca_secret_key="secret",
    )
    base.update(overrides)
    return Settings(**base)


def test_defaults():
    s = _make()
    assert s.symbols == ["SPY"]
    assert s.timeframe == "1Day"
    assert s.max_position_pct == 0.25
    assert s.max_portfolio_drawdown_pct == 0.20
    assert s.stop_loss_pct is None
    assert s.slippage_bps == 5.0


def test_symbols_parsed_from_comma_string():
    s = _make(symbols_raw="spy, qqq ,aapl")
    assert s.symbols == ["SPY", "QQQ", "AAPL"]


def test_symbols_ignores_empty_tokens():
    s = _make(symbols_raw="SPY,,")
    assert s.symbols == ["SPY"]
