"""
Overnight → Intraday Fade (ovn_intraday_v1).

Single pre-specified variant. Fixed parameters — no grid search.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from config.settings import CONTRACTS
from risk.daily_risk_manager import DailyRiskManager
from strategies.base import StrategyBase


class OvernightIntradayFade(StrategyBase):
    """Fade large overnight MES moves at the RTH open within a z-score band."""

    # Fixed v1 parameters (class attributes — no optimizer)
    lookback_days: int = 20
    entry_z: float = 1.0
    band_width_z: float = 0.5
    stop_z: float = 1.5
    target_multiple: float = 1.0
    cooldown_sessions: int = 1

    def __init__(self, risk_manager: DailyRiskManager):
        super().__init__("OvernightIntradayFade", risk_manager)
        self.stop_points_by_bar: Optional[pd.Series] = None
        self.target_points_by_bar: Optional[pd.Series] = None
        self.overnight_z: Optional[pd.Series] = None
        self.params = {
            "lookback_days": self.lookback_days,
            "entry_z": self.entry_z,
            "band_width_z": self.band_width_z,
            "stop_z": self.stop_z,
            "target_multiple": self.target_multiple,
            "cooldown_sessions": self.cooldown_sessions,
        }

    def generate_signals(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        """
        Evaluate once per RTH session at session_start.
        Populates stop_points_by_bar / target_points_by_bar (points).
        """
        required = {"open", "high", "low", "close", "session_start"}
        missing = required - set(data.columns)
        if missing:
            raise ValueError(f"OvernightIntradayFade requires columns {missing}")

        idx = data.index
        signals = pd.Series(0, index=idx, dtype=int)
        stop_pts = pd.Series(np.nan, index=idx, dtype=float)
        target_pts = pd.Series(np.nan, index=idx, dtype=float)
        z_all = pd.Series(np.nan, index=idx, dtype=float)

        session_starts = data.index[data["session_start"].astype(bool)]
        if len(session_starts) < self.lookback_days + 2:
            self.stop_points_by_bar = stop_pts
            self.target_points_by_bar = target_pts
            self.overnight_z = z_all
            return signals

        # Per-session open / close (RTH bars only expected)
        session_id = data["session_start"].astype(bool).cumsum()
        sess_open = data.groupby(session_id)["open"].transform("first")
        sess_close = data.groupby(session_id)["close"].transform("last")

        # One row per session at the session_start bar
        start_mask = data["session_start"].astype(bool)
        opens = sess_open.loc[start_mask]
        closes = sess_close.loc[start_mask]
        prev_close = closes.shift(1)
        ovn_ret = (opens - prev_close) / prev_close

        # σ excluding current session
        sigma = ovn_ret.shift(1).rolling(self.lookback_days, min_periods=self.lookback_days).std()

        z = ovn_ret / sigma
        z_all.loc[start_mask] = z

        lo = self.entry_z
        hi = self.entry_z + self.band_width_z

        direction = pd.Series(0, index=opens.index, dtype=int)
        short_band = (z > lo) & (z <= hi)
        long_band = (z < -lo) & (z >= -hi)
        direction.loc[short_band] = -1
        direction.loc[long_band] = 1

        # Skip sessions with missing prev close / sigma
        invalid = prev_close.isna() | sigma.isna() | (sigma <= 0) | ovn_ret.isna()
        direction.loc[invalid] = 0

        # Cooldown: after a signal session, skip the next cooldown_sessions sessions
        dir_vals = direction.to_numpy().copy()
        cool = 0
        for i in range(len(dir_vals)):
            if cool > 0:
                dir_vals[i] = 0
                cool -= 1
            elif dir_vals[i] != 0:
                cool = self.cooldown_sessions

        direction = pd.Series(dir_vals, index=direction.index)

        # Stop / target in price points at the session open bar
        # stop_distance = stop_z * σ_ovn * previous_close
        stop_distance = self.stop_z * sigma * prev_close
        target_distance = self.target_multiple * stop_distance

        for ts, d in direction.items():
            if d == 0:
                continue
            sd = float(stop_distance.loc[ts])
            td = float(target_distance.loc[ts])
            if not np.isfinite(sd) or sd <= 0:
                continue
            signals.loc[ts] = int(d)
            stop_pts.loc[ts] = sd
            target_pts.loc[ts] = td if np.isfinite(td) and td > 0 else sd

        self.stop_points_by_bar = stop_pts
        self.target_points_by_bar = target_pts
        self.overnight_z = z_all
        return signals

    def size_position(
        self,
        symbol: str,
        signal: int,
        stop_points: float,
        data: Optional[pd.DataFrame] = None,
    ) -> int:
        """
        Size via DailyRiskManager.recommend_size using this trade's stop distance.

        Default recommend_size caps risk at 0.5% of account ($50), which is below
        one MES contract at these overnight-σ stops. Request risk_dollars equal to
        one contract's stop risk, capped by remaining / max planned daily budget.
        """
        if signal == 0 or not self.risk.can_take_new_risk():
            return 0
        if stop_points <= 0:
            return 0
        spec = CONTRACTS[symbol]
        one_contract_risk = float(stop_points) * spec.multiplier
        risk_dollars = min(
            one_contract_risk,
            float(self.risk.remaining_risk_budget),
            float(self.risk.max_planned_risk),
        )
        size = self.risk.recommend_size(
            symbol, stop_points, risk_dollars=risk_dollars
        )
        return size * signal
