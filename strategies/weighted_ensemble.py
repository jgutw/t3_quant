"""
WeightedEnsembleStrategy
Re-implementation of the TradingView multi-indicator ensemble
with proper quantitative hygiene for the T3 prop account.

Key differences from the original indicator:
- Hard accuracy gate (auto-disable on low accuracy)
- Online weight update is regularized and optional
- All signals still have to pass the DailyRiskManager
- Multi-TF filter is a hard permission layer, not just a display
- CPR / ORB used as explicit entry filters
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, Optional, List
from collections import deque

from strategies.base import StrategyBase
from risk.daily_risk_manager import DailyRiskManager
from features.indicators import (
    supertrend, moving_average_signal, vwap_signal,
    linear_regression_signal, session_vwap
)
from features.multi_tf import multi_tf_alignment


class WeightedEnsembleStrategy(StrategyBase):
    def __init__(
        self,
        risk_manager: DailyRiskManager,
        use_adaptive_weights: bool = True,
        learning_rate: float = 0.1,
        lookback: int = 100,
        min_accuracy: float = 0.48,          # hard gate – below this we go flat
        multi_tf_agreement: float = 0.75,    # 75% of higher TFs must agree
        require_cpr_filter: bool = True,
        require_orb_filter: bool = False,
    ):
        super().__init__("WeightedEnsemble", risk_manager)
        self.use_adaptive = use_adaptive_weights
        self.lr = learning_rate
        self.lookback = lookback
        self.min_accuracy = min_accuracy
        self.mtf_agreement = multi_tf_agreement
        self.require_cpr = require_cpr_filter
        self.require_orb = require_orb_filter

        # Equal-weight start (matches the “EQUAL WT” baseline in the screenshot)
        self.weights = {
            "supertrend": 0.25,
            "ma": 0.25,
            "vwap": 0.25,
            "linreg": 0.25,
        }

        # Online performance tracking (for adaptive weights + accuracy gate)
        self.signal_history: Dict[str, deque] = {
            k: deque(maxlen=lookback) for k in self.weights
        }
        self.outcome_history: deque = deque(maxlen=lookback)
        self.current_accuracy: float = 0.5
        self.is_enabled: bool = True

    def _update_weights(self, outcomes: Dict[str, float]) -> None:
        """
        Simple multiplicative-weights style update.
        outcomes[signal_name] = +1 if that signal was correct on the last bar, else -1.
        """
        if not self.use_adaptive:
            return

        for name, correct in outcomes.items():
            # Multiplicative update with learning rate
            self.weights[name] *= np.exp(self.lr * correct)
            self.signal_history[name].append(correct)

        # Renormalize
        total = sum(self.weights.values())
        if total > 0:
            for k in self.weights:
                self.weights[k] /= total

        # Update accuracy estimate
        if self.outcome_history:
            self.current_accuracy = np.mean(self.outcome_history)
            if self.current_accuracy < self.min_accuracy:
                self.is_enabled = False
            else:
                self.is_enabled = True

    def generate_signals(
        self,
        data: pd.DataFrame,
        higher_tf_closes: Optional[Dict[str, pd.Series]] = None,
        cpr_levels: Optional[dict] = None,
        orb_high: Optional[float] = None,
        orb_low: Optional[float] = None,
    ) -> pd.Series:
        """
        data must contain: high, low, close, volume
        and a boolean column 'session_start' marking the first bar of each RTH session.

        Returns target direction Series (+1 / -1 / 0)
        """
        if not self.is_enabled:
            return pd.Series(0, index=data.index)

        # ----- Individual signals -----
        _, st_dir = supertrend(data["high"], data["low"], data["close"])
        ma_dir = moving_average_signal(data["close"])
        vwap = session_vwap(
            data["high"], data["low"], data["close"], data["volume"],
            data["session_start"]
        )
        vwap_dir = vwap_signal(data["close"], vwap)
        linreg_dir, _ = linear_regression_signal(data["close"])

        signals = pd.DataFrame({
            "supertrend": st_dir,
            "ma": ma_dir,
            "vwap": vwap_dir,
            "linreg": linreg_dir,
        })

        # Weighted vote
        raw_score = (
            signals["supertrend"] * self.weights["supertrend"] +
            signals["ma"] * self.weights["ma"] +
            signals["vwap"] * self.weights["vwap"] +
            signals["linreg"] * self.weights["linreg"]
        )

        direction = np.sign(raw_score).fillna(0)

        # ----- Multi-TF permission filter -----
        if higher_tf_closes is not None:
            mtf = multi_tf_alignment(higher_tf_closes, self.mtf_agreement)
            mtf = mtf.reindex(data.index, method="ffill").fillna(0)
            # Only keep the signal when it agrees with the multi-TF regime
            direction = direction.where(direction == mtf, 0)

        # ----- CPR filter -----
        if self.require_cpr and cpr_levels is not None:
            # Accept a single-session dict OR a bar-aligned DataFrame/dict of Series
            if isinstance(cpr_levels, pd.DataFrame):
                tc = cpr_levels["tc"].reindex(data.index)
                bc = cpr_levels["bc"].reindex(data.index)
            elif isinstance(cpr_levels, dict) and any(
                isinstance(v, pd.Series) for v in cpr_levels.values()
            ):
                tc = pd.Series(cpr_levels["tc"]).reindex(data.index)
                bc = pd.Series(cpr_levels["bc"]).reindex(data.index)
            else:
                tc = cpr_levels["tc"]
                bc = cpr_levels["bc"]

            above_tc = data["close"] > tc
            below_bc = data["close"] < bc
            valid = tc.notna() & bc.notna() if hasattr(tc, "notna") else True
            direction = direction.where(valid, 0)
            # Long only above TC, short only below BC
            direction = direction.where(
                ((direction > 0) & above_tc) | ((direction < 0) & below_bc),
                0
            )

        # ----- ORB filter (optional) -----
        if self.require_orb and orb_high is not None and orb_low is not None:
            above_orh = data["close"] > orb_high
            below_orl = data["close"] < orb_low
            direction = direction.where(
                ((direction > 0) & above_orh) | ((direction < 0) & below_orl),
                0
            )

        return direction

    def record_outcome(self, signal_name: str, was_correct: bool) -> None:
        """Call after the fact to update adaptive weights and accuracy."""
        val = 1.0 if was_correct else -1.0
        self.outcome_history.append(1.0 if was_correct else 0.0)
        self._update_weights({signal_name: val})
