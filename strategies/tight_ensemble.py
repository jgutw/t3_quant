"""
MTF-gated equal-weight ensemble with entry tightening (V1.1 research sleeve).
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from features.indicators import session_vwap
from risk.daily_risk_manager import DailyRiskManager
from strategies.entry_filters import tighten_entries
from strategies.weighted_ensemble import WeightedEnsembleStrategy


class TightenedEnsembleStrategy(WeightedEnsembleStrategy):
    """
    Same core signals as WeightedEnsembleStrategy, plus:
      - RTH entry window (default 10:00–11:30)
      - VWAP pullback confirmation
      - Cooldown after exits
    """

    def __init__(
        self,
        risk_manager: DailyRiskManager,
        entry_start: str = "10:00",
        entry_end: str = "11:30",
        require_pullback: bool = True,
        cooldown_bars: int = 6,
        flatten_outside_window: bool = True,
        **kwargs,
    ):
        super().__init__(risk_manager=risk_manager, **kwargs)
        self.name = "TightenedEnsemble"
        self.entry_start = entry_start
        self.entry_end = entry_end
        self.require_pullback = require_pullback
        self.cooldown_bars = cooldown_bars
        self.flatten_outside_window = flatten_outside_window

    def generate_signals(
        self,
        data: pd.DataFrame,
        higher_tf_closes: Optional[Dict[str, pd.Series]] = None,
        cpr_levels: Optional[dict] = None,
        orb_high: Optional[float] = None,
        orb_low: Optional[float] = None,
    ) -> pd.Series:
        raw = super().generate_signals(
            data,
            higher_tf_closes=higher_tf_closes,
            cpr_levels=cpr_levels,
            orb_high=orb_high,
            orb_low=orb_low,
        )
        vwap = session_vwap(
            data["high"],
            data["low"],
            data["close"],
            data["volume"],
            data["session_start"],
        )
        return tighten_entries(
            raw,
            data["close"],
            vwap,
            entry_start=self.entry_start,
            entry_end=self.entry_end,
            require_pullback=self.require_pullback,
            cooldown_bars=self.cooldown_bars,
            flatten_outside_window=self.flatten_outside_window,
        )
