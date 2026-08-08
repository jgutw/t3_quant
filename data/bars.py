"""
Bar resampling and session filters for the research / backtest path.
"""

from __future__ import annotations

import pandas as pd

from data.continuous import add_session_start


def resample_ohlcv(df: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
    """Resample OHLCV and rebuild session_start on the new index."""
    out = (
        df.resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    return add_session_start(out)


def filter_rth(
    df: pd.DataFrame,
    start: str = "09:30",
    end: str = "16:00",
    timezone: str = "America/New_York",
) -> pd.DataFrame:
    """Keep only Regular Trading Hours bars (inclusive start, exclusive end)."""
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize(timezone)
    else:
        idx = idx.tz_convert(timezone)

    out = df.copy()
    out.index = idx
    times = out.index.strftime("%H:%M")
    mask = (times >= start) & (times < end)
    return out.loc[mask].copy()
