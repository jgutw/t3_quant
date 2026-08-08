"""Backtester must feed adverse extremes and never print past hard limit."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.engine import SimpleBacktester
from risk.daily_risk_manager import DailyRiskManager
from strategies.base import StrategyBase


class AlwaysLong(StrategyBase):
    def __init__(self, risk_manager):
        super().__init__("AlwaysLong", risk_manager)

    def generate_signals(self, data, **kwargs):
        return pd.Series(1, index=data.index)


def _bars() -> pd.DataFrame:
    idx = pd.date_range("2025-06-02 09:30", periods=4, freq="5min", tz="America/New_York")
    # Bar 0: enter around 5000
    # Bar 1: catastrophic low that would be -$1000+ on 10 MES without capping
    return pd.DataFrame(
        {
            "open": [5000.0, 5000.0, 4980.0, 4985.0],
            "high": [5002.0, 5001.0, 4985.0, 4990.0],
            "low": [4998.0, 4800.0, 4975.0, 4980.0],  # 200pt air-pocket
            "close": [5000.0, 4985.0, 4982.0, 4988.0],
            "volume": [1000, 1000, 1000, 1000],
            "session_start": [True, False, False, False],
        },
        index=idx,
    )


def test_adverse_bar_cannot_print_past_hard_limit():
    risk = DailyRiskManager()
    strategy = AlwaysLong(risk)
    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=6.0,
        slippage_ticks=0.0,
    )
    result = bt.run(_bars())

    assert result.worst_intraday >= -risk.hard_loss_limit - 1e-6
    assert result.worst_intraday_pnl >= -risk.hard_loss_limit - 1e-6
    # Equity path also never prints past hard limit
    assert float(result.equity_curve.min()) >= -risk.hard_loss_limit - 1e-6


if __name__ == "__main__":
    test_adverse_bar_cannot_print_past_hard_limit()
    print("Backtester adverse-bar hard-limit test passed.")
