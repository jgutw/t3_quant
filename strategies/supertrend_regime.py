"""
SuperTrendRegimeStrategy
Single-regime directional strategy replacing the 4-way ensemble.

Theory of operation:
  - Regime: 15-min SuperTrend sets the ONLY directional input.
  - Entry: optional pullback to session VWAP within the regime.
  - Permission: optional MTF gate (15m + 1h, >=75%).
  - Exit: regime flips / chop, or fixed stop (backtester).

Note: Our SimpleBacktester treats the signal as a *continuous target*
(+1 hold long / -1 hold short / 0 flat). Entry pulses alone would
flatten on the next bar, so this implementation enters on setup and
*holds* while the regime remains valid.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from features.indicators import session_vwap, supertrend
from features.multi_tf import multi_tf_alignment
from risk.daily_risk_manager import DailyRiskManager
from strategies.base import StrategyBase


class SuperTrendRegimeStrategy(StrategyBase):
    """
    Regime: 15-min SuperTrend (10, 3.0)
    Entry: 5-min pullback to session VWAP within regime (optional)
    Permission: MTF gate (optional)
    Exit: Regime flip/chop (signal -> 0) or stop (backtester)
    """

    def __init__(
        self,
        risk_manager: DailyRiskManager,
        st_period: int = 10,
        st_multiplier: float = 3.0,
        min_regime_bars: int = 3,
        entry_window_start: str = "10:00",
        entry_window_end: str = "11:30",
        cooldown_bars: int = 6,
        require_pullback: bool = True,
        use_mtf: bool = True,
        multi_tf_agreement: float = 0.75,
        flatten_outside_window: bool = True,
    ):
        super().__init__("SuperTrendRegime", risk_manager)
        self.st_period = st_period
        self.st_multiplier = st_multiplier
        self.min_regime_bars = min_regime_bars
        self.entry_start = entry_window_start
        self.entry_end = entry_window_end
        self.cooldown_bars = cooldown_bars
        self.require_pullback = require_pullback
        self.use_mtf = use_mtf
        self.multi_tf_agreement = multi_tf_agreement
        self.flatten_outside_window = flatten_outside_window

    def _fifteen_min_regime(self, data: pd.DataFrame) -> pd.Series:
        resampled = (
            data.resample("15min")
            .agg({"high": "max", "low": "min", "close": "last"})
            .dropna()
        )
        _, st_dir = supertrend(
            resampled["high"],
            resampled["low"],
            resampled["close"],
            period=self.st_period,
            multiplier=self.st_multiplier,
        )
        st_dir = st_dir.astype(float)

        # Persist on *native* 15m bars, then map to 5m
        vals = st_dir.to_numpy(dtype=float)
        out = np.zeros(len(vals), dtype=float)
        run = 0
        prev = 0.0
        for i, v in enumerate(vals):
            if v == 0.0:
                run = 0
                prev = 0.0
                continue
            if v == prev:
                run += 1
            else:
                run = 1
                prev = v
            out[i] = v if run >= self.min_regime_bars else 0.0

        persisted = pd.Series(out, index=st_dir.index)
        return persisted.reindex(data.index, method="ffill").fillna(0.0)

    def generate_signals(
        self,
        data: pd.DataFrame,
        higher_tf_closes: Optional[Dict[str, pd.Series]] = None,
        cpr_levels: Optional[dict] = None,
        orb_high: Optional[float] = None,
        orb_low: Optional[float] = None,
    ) -> pd.Series:
        # 1) Regime
        regime = self._fifteen_min_regime(data)

        # 2) Value level
        volume = data["volume"] if "volume" in data.columns else pd.Series(1.0, index=data.index)
        session_start = (
            data["session_start"]
            if "session_start" in data.columns
            else pd.Series(False, index=data.index)
        )
        vwap = session_vwap(
            data["high"], data["low"], data["close"], volume, session_start
        )

        close = data["close"].to_numpy(dtype=float)
        low = data["low"].to_numpy(dtype=float)
        high = data["high"].to_numpy(dtype=float)
        vwap_a = vwap.to_numpy(dtype=float)
        regime_a = regime.to_numpy(dtype=float)
        times = data.index.strftime("%H:%M")

        # Optional MTF series (permission applied at entry and for hold)
        if self.use_mtf and higher_tf_closes is not None:
            mtf = multi_tf_alignment(
                higher_tf_closes, required_agreement=self.multi_tf_agreement
            )
            mtf_a = mtf.reindex(data.index, method="ffill").fillna(0.0).to_numpy(dtype=float)
        else:
            mtf_a = None

        out = np.zeros(len(data), dtype=float)
        state = 0.0
        cooldown = 0

        for i in range(len(data)):
            r = regime_a[i]
            in_window = self.entry_start <= times[i] < self.entry_end

            if cooldown > 0:
                cooldown -= 1

            # Permission: when MTF is on, regime must match MTF
            permitted = True
            if mtf_a is not None:
                permitted = r != 0.0 and r == mtf_a[i]
                if not permitted:
                    r = 0.0

            # ----- Hold / exit -----
            if state != 0.0:
                leave = r == 0.0 or np.sign(r) != np.sign(state)
                if self.flatten_outside_window and not in_window:
                    leave = True
                if leave:
                    state = 0.0
                    cooldown = self.cooldown_bars
                out[i] = state
                continue

            # ----- Flat: entry -----
            if r == 0.0 or not in_window or cooldown > 0:
                out[i] = 0.0
                continue

            if self.require_pullback:
                v = vwap_a[i]
                if not np.isfinite(v):
                    out[i] = 0.0
                    continue
                # Spec: touch VWAP AND close on value side of VWAP
                long_setup = (r > 0) and (low[i] <= v) and (close[i] <= v)
                short_setup = (r < 0) and (high[i] >= v) and (close[i] >= v)
                if not (long_setup or short_setup):
                    out[i] = 0.0
                    continue

            state = float(np.sign(r))
            out[i] = state

        return pd.Series(out, index=data.index, name="st_regime_signal")
