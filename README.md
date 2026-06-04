# algotrader

A modular **paper-trading** algorithmic trading + backtesting harness, built for
learning the engineering. The objective is a *trustworthy evaluation harness* —
not profitability.

> **PAPER MONEY ONLY.** No live / real-money order-routing code exists in this
> repository. `AlpacaPaperBroker` hardwires `paper=True` with no switch.

---

## Prime directives (all honoured)

| # | Directive | Where enforced |
|---|-----------|---------------|
| 1 | Paper money only — no live path | `AlpacaPaperBroker`: `paper=True` hardwired |
| 2 | No look-ahead bias | `BacktestEngine`: `bars[:i+1]` slice; proven by `test_engine_has_no_lookahead_bias` |
| 3 | Every strategy measured against BuyAndHold honestly | `BacktestEngine.run()` always produces a benchmark curve; `print_report` always shows both |
| 4 | Secrets in `.env`, never logged | `config.py` reads from env; logging never references credential fields |
| 5 | SDK verified before coding | `alpaca-py 0.43.4` confirmed against installed package |

---

## Architecture

```
algotrader/
  config.py            # all settings from .env (single source of truth)
  logging_config.py    # structlog setup

  broker/
    models.py          # broker-agnostic domain types
    base.py            # abstract Broker interface
    alpaca_paper.py    # AlpacaPaperBroker (paper=True hardwired)

  data/
    client.py          # MarketDataClient — single source of truth for "data at time T"
    cache.py           # DuckDB BarCache

  strategy/
    base.py            # abstract Strategy: generate_signals(bars) -> {sym: weight}
    buy_and_hold.py    # BuyAndHold — the required benchmark
    sma_crossover.py   # SmaCrossover(fast, slow) — parameterized
    llm_strategy.py    # LlmStrategy — Phase 6 experimental (Claude via Anthropic API)

  backtest/
    portfolio.py       # Portfolio state (cash, positions, avg_entry_prices, trades)
    engine.py          # bar-by-bar BacktestEngine (no look-ahead, fills at next open)
    walk_forward.py    # WalkForwardSplitter — expanding-window + holdout

  metrics/
    calculator.py      # total_return, CAGR, Sharpe, Sortino, max_drawdown, ...

  risk/
    manager.py         # RiskManager: position cap, drawdown kill-switch, stop-loss

  orchestration/
    live_loop.py       # one trading cycle: data → signals → risk → reconcile → order
    scheduler.py       # APScheduler wrapper (BlockingScheduler, interval-based)

  reporting/
    storage.py         # DuckDB: runs, trades, equity_curve, metrics tables
    report.py          # print_report, save_equity_plot, persist_result

scripts/
  smoke_test.py        # Phase 1: auth + bars + clock + tiny paper order round-trip
  backtest_run.py      # Phase 3: walk-forward backtest with honest metrics table
  run_live.py          # Phase 4: live paper-trading loop (runs until Ctrl-C)
  report.py            # Phase 5: CLI report from stored results + equity plot

tests/                 # 52 tests, fully offline (no keys / network)
  test_backtest.py     # ← includes the no-look-ahead sentinel test
  test_risk.py
  test_metrics.py
  test_strategies.py
  test_broker_models.py
  test_cache.py
  test_config.py
```

---

## Verified SDK

Integration written against **`alpaca-py` 0.43.4** (current). Confirmed against
the installed package (not from memory): `paper` param, `get_all_positions`,
`get_open_position`, `submit_order(order_data=...)`, `cancel_order_by_id`,
`close_position`, `get_clock`, `StockHistoricalDataClient`, `StockBarsRequest`,
`TimeFrame`.

---

## Dependencies

| Package | Why |
|---------|-----|
| `alpaca-py` | Official Alpaca SDK: paper broker + historical data |
| `pydantic-settings` | Typed config from `.env` |
| `pandas` | Bar/time-series handling |
| `numpy` | Metrics arithmetic |
| `duckdb` | Market-data cache + results store |
| `structlog` | Structured logging |
| `APScheduler 3.x` | Live-loop scheduling (v4 has different API) |
| `matplotlib` | Equity-curve plots (Agg backend; no display required) |
| `anthropic` | Claude API for Phase 6 LLM strategy |
| `pytest` | Tests |

---

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env
# Edit .env — paste ALPACA_API_KEY and ALPACA_SECRET_KEY (paper account only)
```

---

## How to run each phase

### Phase 1 — Connectivity smoke test

```bash
# Offline: 11 unit tests (no keys/network)
python -m pytest

# Full: auth, fetch bars, clock, place+unwind 1 paper order
python -m scripts.smoke_test --dry-run   # skip orders
python -m scripts.smoke_test
```

### Phase 2 — Strategy signals (offline)

```bash
python -m pytest tests/test_strategies.py -v
```

### Phase 3 — Walk-forward backtest (needs Alpaca data API keys)

```bash
# Default: SmaCrossover on SPY, Jan 2018 → today
python -m scripts.backtest_run

# Custom range, with plot and persistence
python -m scripts.backtest_run \
  --symbol SPY \
  --start 2018-01-01 \
  --end   2023-12-31 \
  --strategy sma_crossover \
  --fast 20 --slow 50 \
  --plot --save

# Expected output: honest metrics table for each fold + holdout.
# Includes the no-look-ahead test (in the test suite).
```

The no-look-ahead proof:
```bash
python -m pytest tests/test_backtest.py::test_engine_has_no_lookahead_bias -v
```

### Phase 4 — Live paper loop (needs keys; market hours)

```bash
# Dry-run: log what would be ordered, no actual orders
python -m scripts.run_live --dry-run

# Full: places paper orders every 5 minutes during market hours (Ctrl-C to stop)
python -m scripts.run_live --strategy sma_crossover
```

### Phase 5 — Performance report

```bash
# List recent runs + print metrics for the latest one
python -m scripts.report

# Specific run with equity-curve PNG
python -m scripts.report --run-id <id> --plot
```

### Phase 6 — LLM strategy (optional; needs `ANTHROPIC_API_KEY` in `.env`)

```bash
# Backtest Claude vs SmaCrossover vs BuyAndHold
python -m scripts.backtest_run --strategy llm --start 2022-01-01 --end 2023-12-31

# Live paper loop driven by Claude
python -m scripts.run_live --strategy llm
```

The LLM strategy:
- Receives the same point-in-time OHLCV data every other strategy sees
- Caches API calls by content hash (avoids redundant cost on repeated backtests)
- Falls back to flat/cash on any API error
- Never bypasses the risk module

---

## Correctness notes

**Survivorship bias**: the default `SPY` universe is a single ETF that tracks the
S&P 500. The S&P 500 itself has survivorship bias (failed companies are removed).
Any additional symbols you add should be chosen carefully — hand-picking known
survivors inflates results. This is documented in `BuyAndHold`.

**Transaction costs**: slippage is modelled as a configurable number of basis
points applied asymmetrically to fill prices. Alpaca paper is commission-free,
but the slippage model (default 5 bps) produces realistic cost drag.

**No in-sample reporting**: the `backtest_run` script reports only out-of-sample
fold results and the final holdout. In-sample results are explicitly labelled as
such and not used for performance claims.
