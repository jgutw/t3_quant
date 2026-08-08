"""
Multi-timeframe trend alignment filter.
Mirrors the 3m / 5m / 15m / 1h / 1d confluence panel from the TradingView indicator.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Dict, List


def higher_tf_trend(
    close: pd.Series,
    method: str = "ema",
    fast: int = 8,
    slow: int = 21
) -> pd.Series:
    """
    Simple trend direction on a single series.
    +1 bullish, -1 bearish, 0 neutral / insufficient data.
    """
    if method == "ema":
        f = close.ewm(span=fast, adjust=False).mean()
        s = close.ewm(span=slow, adjust=False).mean()
        return np.sign(f - s).fillna(0)
    else:
        # fallback: linear regression slope sign
        def slope_sign(y):
            if len(y) < slow or np.any(np.isnan(y)):
                return 0.0
            x = np.arange(len(y))
            slope = np.polyfit(x, y, 1)[0]
            return np.sign(slope)
        return close.rolling(slow).apply(slope_sign, raw=True).fillna(0)


def multi_tf_alignment(
    tf_closes: Dict[str, pd.Series],
    required_agreement: float = 1.0
) -> pd.Series:
    """
    tf_closes: dict of {timeframe_name: close_series}
               e.g. {"5m": df_5m.close, "15m": df_15m.close, "1h": ..., "1d": ...}

    Returns a Series (indexed to the lowest TF) that is True only when
    the fraction of higher timeframes that agree on direction >= required_agreement.

    Typical usage for the T3 account:
        required_agreement = 0.75  (at least 3 out of 4 higher TFs agree)
        or 1.0 for the strict “all must align” behaviour of the original indicator.
    """
    if not tf_closes:
        raise ValueError("tf_closes must contain at least one series")

    # Use the shortest timeframe as the master index
    master_name = min(tf_closes.keys(), key=lambda k: len(tf_closes[k]))
    master = tf_closes[master_name]
    master_idx = master.index

    directions = {}
    for name, series in tf_closes.items():
        dir_ = higher_tf_trend(series)
        # Align to master index (forward-fill higher TF values)
        directions[name] = dir_.reindex(master_idx, method="ffill").fillna(0)

    dir_df = pd.DataFrame(directions)
    # Count how many are bullish / bearish
    bull_count = (dir_df > 0).sum(axis=1)
    bear_count = (dir_df < 0).sum(axis=1)
    total = len(tf_closes)

    alignment = pd.Series(0, index=master_idx)
    alignment[bull_count / total >= required_agreement] = 1
    alignment[bear_count / total >= required_agreement] = -1

    return alignment
