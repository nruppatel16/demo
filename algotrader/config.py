"""Typed application configuration, loaded from `.env` via pydantic-settings.

This is the single, central home for credentials, the tradable universe, risk
parameters, and backtest assumptions. Nothing else in the codebase should read
environment variables directly.
"""

from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Strongly-typed settings sourced from environment / `.env`.

    Field names map case-insensitively to env vars (e.g. ``alpaca_api_key`` <-
    ``ALPACA_API_KEY``). See ``.env.example`` for the full list.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        populate_by_name=True,  # allow both `symbols_raw=...` and SYMBOLS env var
    )

    # --- Alpaca paper credentials (paper keys only; no live path exists) ---
    alpaca_api_key: str
    alpaca_secret_key: str

    # --- Universe & data ---
    # Stored as a raw string and exposed as a parsed list via ``symbols`` so the
    # user can write a simple comma-separated value in `.env` (no JSON required).
    symbols_raw: str = Field(default="SPY", alias="SYMBOLS")
    timeframe: str = "1Day"
    data_dir: str = "data_store"

    # --- Risk parameters (applied uniformly to backtest AND live) ---
    max_position_pct: float = 0.25
    max_portfolio_drawdown_pct: float = 0.20
    stop_loss_pct: float | None = None

    # --- Backtest assumptions ---
    slippage_bps: float = 5.0

    # --- Logging ---
    log_level: str = "INFO"
    log_json: bool = False

    @property
    def symbols(self) -> list[str]:
        """Tradable universe as an upper-cased list of tickers."""
        return [s.strip().upper() for s in self.symbols_raw.split(",") if s.strip()]


def load_settings() -> Settings:
    """Construct :class:`Settings` from the environment / `.env`.

    Kept as a function (rather than a module-level singleton) so tests can
    construct ``Settings`` with explicit values without import-time side effects.
    """
    return Settings()  # type: ignore[call-arg]  # values come from env/.env
