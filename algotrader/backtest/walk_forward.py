"""Walk-forward validation: expanding-window splits + holdout.

Structure:
    Full dataset: [start ... end]
    Holdout (last holdout_frac of data): NEVER touched until final evaluation
    Walk-forward folds on the non-holdout slice:
        Fold 1: train=[0..min_train], test=[min_train..min_train+step]
        Fold 2: train=[0..min_train+step], test=[min_train+step..min_train+2*step]
        ...  (expanding window: train always starts at 0)

For SmaCrossover the "train" phase is trivial (no parameter fitting), but the
structure supports parameter search in future phases.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

import pandas as pd


@dataclass
class WalkForwardSplit:
    fold: int
    train_start: datetime
    train_end: datetime
    test_start: datetime
    test_end: datetime


class WalkForwardSplitter:
    """Generate expanding-window train/test splits from a DatetimeIndex.

    Args:
        min_train_frac: fraction of non-holdout data used for the first fold's
            training window (default 0.5 = first half trains, second half tests).
        n_folds: number of walk-forward folds.
        holdout_frac: fraction of *total* data kept as a never-touched holdout.
    """

    def __init__(
        self,
        min_train_frac: float = 0.5,
        n_folds: int = 4,
        holdout_frac: float = 0.2,
    ) -> None:
        if not 0 < holdout_frac < 1:
            raise ValueError("holdout_frac must be in (0, 1)")
        if not 0 < min_train_frac < 1:
            raise ValueError("min_train_frac must be in (0, 1)")
        self.min_train_frac = min_train_frac
        self.n_folds = n_folds
        self.holdout_frac = holdout_frac

    def split(
        self, index: pd.DatetimeIndex
    ) -> tuple[list[WalkForwardSplit], datetime, datetime]:
        """Return (folds, holdout_start, holdout_end).

        ``index`` is sorted ascending. The last ``holdout_frac`` of dates form
        the holdout; the rest are used for walk-forward.
        """
        n = len(index)
        holdout_n = max(1, int(n * self.holdout_frac))
        wf_index = index[: n - holdout_n]
        holdout_index = index[n - holdout_n :]

        wf_n = len(wf_index)
        min_train_n = max(1, int(wf_n * self.min_train_frac))
        test_total = wf_n - min_train_n
        step = max(1, test_total // self.n_folds)

        folds: list[WalkForwardSplit] = []
        for fold_i in range(self.n_folds):
            test_start_idx = min_train_n + fold_i * step
            test_end_idx = min(test_start_idx + step, wf_n)
            if test_start_idx >= wf_n:
                break
            folds.append(
                WalkForwardSplit(
                    fold=fold_i + 1,
                    train_start=wf_index[0].to_pydatetime(),
                    train_end=wf_index[test_start_idx - 1].to_pydatetime(),
                    test_start=wf_index[test_start_idx].to_pydatetime(),
                    test_end=wf_index[test_end_idx - 1].to_pydatetime(),
                )
            )

        return (
            folds,
            holdout_index[0].to_pydatetime(),
            holdout_index[-1].to_pydatetime(),
        )
