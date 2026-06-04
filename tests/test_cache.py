"""BarCache round-trip + upsert tests (offline; real DuckDB)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from algotrader.data.cache import BarCache


def _frame(start: datetime, n: int, close_start: float = 100.0) -> pd.DataFrame:
    idx = pd.DatetimeIndex(
        [start + timedelta(days=i) for i in range(n)], name="timestamp"
    )
    return pd.DataFrame(
        {
            "open": [close_start + i for i in range(n)],
            "high": [close_start + i + 1 for i in range(n)],
            "low": [close_start + i - 1 for i in range(n)],
            "close": [close_start + i for i in range(n)],
            "volume": [1000 + i for i in range(n)],
        },
        index=idx,
    )


def test_write_then_read_roundtrip(tmp_path):
    cache = BarCache(str(tmp_path))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cache.write("SPY", "1Day", _frame(start, 5))

    out = cache.read("SPY", "1Day", start, start + timedelta(days=4))
    assert len(out) == 5
    assert list(out.columns) == ["open", "high", "low", "close", "volume"]
    assert out["close"].iloc[0] == 100.0
    assert out["close"].iloc[-1] == 104.0


def test_read_empty_when_absent(tmp_path):
    cache = BarCache(str(tmp_path))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    out = cache.read("AAPL", "1Day", start, start + timedelta(days=5))
    assert out.empty


def test_upsert_does_not_duplicate(tmp_path):
    cache = BarCache(str(tmp_path))
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)

    cache.write("SPY", "1Day", _frame(start, 5))
    # Overlapping rewrite with different closes should replace, not duplicate.
    cache.write("SPY", "1Day", _frame(start + timedelta(days=2), 5, close_start=200.0))

    out = cache.read("SPY", "1Day", start, start + timedelta(days=10))
    # Days 0-1 original (100,101) + days 2-6 rewritten (200..204) = 7 unique rows.
    assert len(out) == 7
    assert out["close"].iloc[0] == 100.0
    assert out["close"].iloc[2] == 200.0
