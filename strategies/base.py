"""
StrategyBase – common interface for every system we build.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import pandas as pd

from risk.daily_risk_manager import DailyRiskManager


class StrategyBase(ABC):
    """
    All strategies must implement generate_signals and respect the risk manager.
    """

    def __init__(self, name: str, risk_manager: DailyRiskManager):
        self.name = name
        self.risk = risk_manager
        self.params: Dict[str, Any] = {}

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Return a Series of target position direction:
            +1 long, -1 short, 0 flat
        Indexed the same as data.
        """
        pass

    def size_position(
        self,
        symbol: str,
        signal: int,
        stop_points: float,
        data: Optional[pd.DataFrame] = None
    ) -> int:
        """
        Convert a directional signal into a contract quantity
        that respects the DailyRiskManager.
        """
        if signal == 0 or not self.risk.can_take_new_risk():
            return 0
        size = self.risk.recommend_size(symbol, stop_points)
        return size * signal   # signed quantity

    def on_bar(self, bar: pd.Series, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Optional hook for live / event-driven use.
        Returns a dict that may contain 'order' instructions.
        """
        return {}
