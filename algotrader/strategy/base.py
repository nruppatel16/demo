"""Abstract Strategy interface.

All strategies must implement ``generate_signals``, which maps a snapshot of
point-in-time market data to target portfolio weights.

Contract:
- ``bars`` maps symbol -> DataFrame with OHLCV columns indexed by timestamp.
  The DataFrame contains ONLY bars at or before the current decision time.
  Strategies must NOT read ahead.
- Return value: symbol -> target weight in [0.0, 1.0]. Weights may be reduced
  further by the risk module. Long-only; negative weights are not supported.
- If a symbol is absent from the return dict, target weight is treated as 0.0.
- It is legal to return an empty dict (stay flat).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class Strategy(ABC):
    name: str = "base"

    @abstractmethod
    def generate_signals(
        self, bars: dict[str, pd.DataFrame]
    ) -> dict[str, float]:
        """Return target weights for each symbol, given current-bar data only."""
