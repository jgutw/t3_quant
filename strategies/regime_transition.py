"""
Regime-transition fade (regime_transition_v1).

Transition state: fade the break for up to H bars.
Normal state: flat.
"""

from __future__ import annotations

from typing import Optional

import numpy as np
import pandas as pd

from config.settings import CONTRACTS
from features.indicators import atr
from features.regime_transition import RegimeTransitionParams, compute_transition_z
from risk.daily_risk_manager import DailyRiskManager
from strategies.base import StrategyBase


class RegimeTransitionFade(StrategyBase):
    """Fade CUSUM-style regime breaks inside a short transition window."""

    # Fixed v1 parameters
    L: int = 12
    W: int = 78
    theta: float = 2.0
    H: int = 6
    C: int = 6
    atr_period: int = 20
    stop_atr_mult: float = 1.5
    target_multiple: float = 1.0

    def __init__(self, risk_manager: DailyRiskManager):
        super().__init__("RegimeTransitionFade", risk_manager)
        self.stop_points_by_bar: Optional[pd.Series] = None
        self.target_points_by_bar: Optional[pd.Series] = None
        self.transition_z: Optional[pd.Series] = None
        self.fire_events: Optional[pd.Series] = None
        self.params = {
            "L": self.L,
            "W": self.W,
            "theta": self.theta,
            "H": self.H,
            "C": self.C,
            "atr_period": self.atr_period,
            "stop_atr_mult": self.stop_atr_mult,
            "target_multiple": self.target_multiple,
        }

    def generate_signals(self, data: pd.DataFrame, **kwargs) -> pd.Series:
        required = {"open", "high", "low", "close"}
        missing = required - set(data.columns)
        if missing:
            raise ValueError(f"RegimeTransitionFade requires columns {missing}")

        idx = data.index
        n = len(data)
        signals = pd.Series(0, index=idx, dtype=int)
        stop_pts = pd.Series(np.nan, index=idx, dtype=float)
        target_pts = pd.Series(np.nan, index=idx, dtype=float)

        det = compute_transition_z(
            data["close"],
            RegimeTransitionParams(
                L=self.L, W=self.W, theta=self.theta, H=self.H, C=self.C
            ),
        )
        atr_pts = atr(data["high"], data["low"], data["close"], self.atr_period)

        fire_idx = np.flatnonzero(det["fire"].to_numpy())
        for i in fire_idx:
            entry_i = i + 1  # next-bar open entry
            if entry_i >= n:
                continue
            z_sign = float(det["fire_sign"].iloc[i])
            if z_sign == 0.0 or not np.isfinite(z_sign):
                continue
            direction = int(-np.sign(z_sign))  # fade the break
            stop_dist = float(self.stop_atr_mult * atr_pts.iloc[i])
            if not np.isfinite(stop_dist) or stop_dist <= 0:
                continue
            target_dist = float(self.target_multiple * stop_dist)

            # Only one signal per fire; skip if entry bar already claimed
            if signals.iloc[entry_i] != 0:
                continue
            signals.iloc[entry_i] = direction
            stop_pts.iloc[entry_i] = stop_dist
            target_pts.iloc[entry_i] = target_dist

        self.stop_points_by_bar = stop_pts
        self.target_points_by_bar = target_pts
        self.transition_z = det["z"]
        self.fire_events = det["fire"]
        return signals

    def size_position(
        self,
        symbol: str,
        signal: int,
        stop_points: float,
        data: Optional[pd.DataFrame] = None,
    ) -> int:
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
