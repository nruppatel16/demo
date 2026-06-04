"""Phase 6 — LLM Strategy (experimental).

Uses a Claude model to recommend portfolio allocation weights given recent
point-in-time OHLCV data. Its ONLY purpose is benchmarking head-to-head
against SmaCrossover and BuyAndHold.

Key properties:
  - Implements the same ``Strategy`` interface as every other strategy.
  - Sees only the same data every other strategy sees (no special context).
  - Every call is cached by a hash of the input data (avoids redundant API cost).
  - Never bypasses the risk module.
  - Falls back to flat (0.0 for all symbols) on any API error.

Cost note: at ~$0.25/M input tokens, a 20-bar lookback for 1 symbol is roughly
$0.000025 per call. Over 5 years of daily bars (~1260 calls), that's ~$0.03.
Caching eliminates most of this in repeated backtests.
"""

from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime

import pandas as pd

from algotrader.logging_config import get_logger
from algotrader.strategy.base import Strategy

log = get_logger("llm_strategy")


class LlmStrategy(Strategy):
    """Allocates portfolio weights by asking a Claude model.

    The model receives a compact summary of recent OHLCV data and is asked
    to respond with a JSON dict of {symbol: weight}. Invalid/missing responses
    fall back to flat (all zeros).
    """

    name = "llm"

    def __init__(
        self,
        api_key: str,
        symbols: list[str],
        lookback_bars: int = 20,
        model: str = "claude-haiku-4-5-20251001",
        cache_dir: str = "llm_cache",
    ) -> None:
        self._api_key = api_key
        self._symbols = symbols
        self._lookback = lookback_bars
        self._model = model
        self._cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.name = f"llm_{model.split('-')[1]}"  # e.g. llm_haiku

    def generate_signals(self, bars: dict[str, pd.DataFrame]) -> dict[str, float]:
        if not bars:
            return {}

        # Clip to lookback window
        clipped = {
            sym: df.iloc[-self._lookback:] for sym, df in bars.items() if not df.empty
        }
        if not clipped:
            return {sym: 0.0 for sym in bars}

        cache_key = self._cache_key(clipped)
        cached = self._read_cache(cache_key)
        if cached is not None:
            return cached

        prompt = self._build_prompt(clipped)
        result = self._call_api(prompt, cache_key)
        return result

    def _build_prompt(self, bars: dict[str, pd.DataFrame]) -> str:
        parts = [
            "You are analyzing stock market data to set portfolio allocation weights.",
            f"Current date: {datetime.now().date()}",
            f"Universe: {', '.join(bars.keys())}",
            "",
            "Recent daily OHLCV data (oldest → newest):",
        ]
        for sym, df in bars.items():
            parts.append(f"\n{sym} (last {len(df)} trading days):")
            parts.append("  Date        Close   Volume    Return%")
            prev_close = None
            for ts, row in df.iterrows():
                ret = (row["close"] / prev_close - 1) * 100 if prev_close else 0.0
                parts.append(
                    f"  {str(ts)[:10]}  {row['close']:7.2f}  {int(row['volume']):8d}  {ret:+.2f}%"
                )
                prev_close = row["close"]

        last_closes = {sym: float(df.iloc[-1]["close"]) for sym, df in bars.items()}
        sma20 = {}
        for sym, df in bars.items():
            if len(df) >= 20:
                sma20[sym] = float(df["close"].iloc[-20:].mean())

        parts += [
            "",
            "Latest closes: " + ", ".join(f"{s}=${v:.2f}" for s, v in last_closes.items()),
        ]
        if sma20:
            parts.append("20d SMA:       " + ", ".join(f"{s}=${v:.2f}" for s, v in sma20.items()))

        parts += [
            "",
            "Task: Return portfolio allocation weights as a JSON object.",
            "Rules:",
            "  - Weights are floats in [0.0, 1.0]",
            "  - All weights combined must sum to at most 1.0",
            "  - Long-only (no shorting; do not use negative weights)",
            "  - Be conservative; preserve capital",
            "",
            f'Respond with ONLY a JSON object. Example: {{"{list(bars)[0]}": 0.6}}',
        ]
        return "\n".join(parts)

    def _call_api(self, prompt: str, cache_key: str) -> dict[str, float]:
        try:
            import anthropic
            client = anthropic.Anthropic(api_key=self._api_key)
            message = client.messages.create(
                model=self._model,
                max_tokens=256,
                messages=[{"role": "user", "content": prompt}],
            )
            raw = message.content[0].text.strip()
            log.debug("llm_response", raw=raw[:200])
            weights = self._parse_response(raw)
            self._write_cache(cache_key, weights)
            return weights
        except Exception as exc:
            log.warning("llm_api_error", error=str(exc), fallback="flat")
            return {sym: 0.0 for sym in self._symbols}

    def _parse_response(self, text: str) -> dict[str, float]:
        """Extract a JSON dict of {symbol: float} from LLM response text."""
        try:
            # Strip markdown code fences if present
            if "```" in text:
                text = text.split("```")[1].lstrip("json").strip()
            data = json.loads(text)
            result: dict[str, float] = {}
            total = 0.0
            for sym in self._symbols:
                w = float(data.get(sym, 0.0))
                w = max(0.0, min(w, 1.0))
                result[sym] = w
                total += w
            # Normalize if total > 1.0 (never let LLM exceed full investment)
            if total > 1.0:
                result = {sym: w / total for sym, w in result.items()}
            return result
        except Exception as exc:
            log.warning("llm_parse_error", error=str(exc), text=text[:200])
            return {sym: 0.0 for sym in self._symbols}

    # --- Cache (keyed by hash of input data; day-scoped TTL via date prefix) ---

    def _cache_key(self, bars: dict[str, pd.DataFrame]) -> str:
        today = str(datetime.now().date())
        fingerprint = today + "|" + "|".join(
            sym + ":" + ",".join(f"{v:.4f}" for v in df["close"].values)
            for sym, df in sorted(bars.items())
        )
        return hashlib.sha256(fingerprint.encode()).hexdigest()[:16]

    def _cache_path(self, key: str) -> str:
        return os.path.join(self._cache_dir, f"{key}.json")

    def _read_cache(self, key: str) -> dict[str, float] | None:
        path = self._cache_path(key)
        if os.path.exists(path):
            try:
                with open(path) as f:
                    return json.load(f)
            except Exception:
                pass
        return None

    def _write_cache(self, key: str, weights: dict[str, float]) -> None:
        try:
            with open(self._cache_path(key), "w") as f:
                json.dump(weights, f)
        except Exception as exc:
            log.warning("llm_cache_write_error", error=str(exc))
