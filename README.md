# algotrader

A modular **paper-trading** algorithmic trading + backtesting harness, built for
learning the engineering. The objective is a *trustworthy evaluation harness* —
not profitability.

> **PAPER MONEY ONLY.** There is no live / real-money order-routing code in this
> repository. The `Broker` interface exists so a real broker *could* be added
> later, but no live implementation is provided, and the paper broker hardwires
> `paper=True` with no switch to flip.

## Prime directives

1. Paper money only — no live path exists (absent, not flagged off).
2. No look-ahead bias in backtesting (proven by test — arriving in Phase 3).
3. Every strategy measured against a buy-and-hold benchmark, reported honestly.
4. Secrets live in `.env` (git-ignored), never hardcoded or logged.
5. SDK details verified against current official docs before integration.

## Verified SDK (checked, not memorized)

Integration code was written against **`alpaca-py` 0.43.4** (the current official
SDK; the older `alpaca-trade-api` is deprecated). Confirmed against the installed
package: `TradingClient(key, secret, paper=True)`, `get_account`,
`get_all_positions`, `get_open_position`, `submit_order(order_data=...)`,
`cancel_order_by_id`, `close_position`, `get_clock`; data via
`StockHistoricalDataClient` + `StockBarsRequest` + `TimeFrame`.

## Dependencies (lean; each justified)

| Package            | Why |
|--------------------|-----|
| `alpaca-py`        | Official Alpaca SDK — paper broker + historical market data |
| `pydantic-settings`| Typed config loaded from `.env` |
| `pandas`           | Bar / time-series handling (also an `alpaca-py` dependency) |
| `duckdb`           | Local market-data + history cache |
| `structlog`        | Structured (console or JSON) logging |
| `pytest`           | Tests |

Heavier deps (APScheduler, plotting, any backtest library) are deferred to the
phases that actually need them.

## Project layout

```
algotrader/
  config.py            # typed settings from .env (single source of config)
  logging_config.py    # structlog setup
  broker/
    models.py          # broker-agnostic domain types (Account/Position/Order/...)
    base.py            # abstract Broker interface
    alpaca_paper.py    # AlpacaPaperBroker (paper=True hardwired)
  data/
    client.py          # MarketDataClient: Alpaca bars + cache (source of truth
                        #   for "what data existed at time T")
    cache.py           # BarCache: DuckDB-backed OHLCV cache
scripts/
  smoke_test.py        # Phase 1 deliverable (connectivity round-trip)
tests/                 # pytest suite (offline; no keys/network needed)
```

The `Broker` interface is defined purely over the domain models in
`broker/models.py`, so swapping brokers later is a one-file change.

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env and paste your Alpaca PAPER keys
```

## Phase 1 — how to run & verify

**Offline (no keys needed) — the test suite:**

```bash
python -m pytest
# 11 passed: config parsing, SDK->domain conversions, DuckDB cache round-trip/upsert
```

**Connectivity round-trip (needs your paper keys in `.env`):**

```bash
# Safe: account info + bars + clock, no orders placed
python -m scripts.smoke_test --dry-run

# Full: also places ONE tiny paper order, then cancels it (or, if the market is
# open and it filled, liquidates it) so the account is left flat
python -m scripts.smoke_test
```

Expected: structured log lines for `account`, `bars_fetched` / `latest_bar`,
`clock`, and (non-dry-run) `order_submitted` -> `order_canceled` (or
`position_closed`), ending in `smoke_test_complete status=ok`.

## Roadmap

- **Phase 1 — Scaffolding & connectivity** ✅ (this commit)
- **Phase 2** — `Strategy` interface, `BuyAndHold`, `SmaCrossover`
- **Phase 3** — bar-by-bar backtest engine (no look-ahead, **with the proving
  test**), costs/slippage, walk-forward + holdout, metrics
- **Phase 4** — risk module + scheduler + live paper loop
- **Phase 5** — logging/persistence/reporting (DuckDB history, equity-curve plot)
- **Phase 6 (optional)** — `LlmStrategy`, benchmarked head-to-head vs SMA / B&H
