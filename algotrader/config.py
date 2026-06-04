"""Typed application configuration, loaded from `.env` via pydantic-settings.

Single, central home for every tunable: credentials, universe, risk parameters,
strategy params, and backtest assumptions. Nothing else in the codebase reads
env vars directly.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,
    )

    # --- Alpaca paper credentials ---
    alpaca_api_key: str
    alpaca_secret_key: str

    # --- Universe & data ---
    symbols_raw: str = Field(default="SPY", alias="SYMBOLS")
    timeframe: str = "1Day"
    data_dir: str = "data_store"

    # --- Backtest ---
    initial_capital: float = 100_000.0

    # --- Strategy ---
    strategy_name: str = "sma_crossover"   # sma_crossover | buy_and_hold | llm
    sma_fast_window: int = 20
    sma_slow_window: int = 50

    # --- Risk (applied uniformly to backtest AND live) ---
    max_position_pct: float = 0.25
    max_portfolio_drawdown_pct: float = 0.20
    stop_loss_pct: float | None = None

    # --- Backtest assumptions ---
    slippage_bps: float = 5.0

    # --- Live scheduling ---
    schedule_interval_minutes: int = 5

    # --- Logging ---
    log_level: str = "INFO"
    log_json: bool = False

    # --- Phase 6: LLM strategy (optional) ---
    anthropic_api_key: str | None = None
    llm_model: str = "claude-haiku-4-5-20251001"
    llm_lookback_bars: int = 20
    llm_cache_dir: str = "llm_cache"

    @property
    def symbols(self) -> list[str]:
        return [s.strip().upper() for s in self.symbols_raw.split(",") if s.strip()]


def load_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
