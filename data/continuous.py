"""
Continuous contract utilities.
Placeholder for the real data pipeline (Databento / Rithmic historical / CME DataMine).
"""

from __future__ import annotations
import pandas as pd
from pathlib import Path
from typing import Optional


def load_parquet(path: str | Path) -> pd.DataFrame:
    """
    Expected columns: datetime (index), open, high, low, close, volume
    Optional: session_start (bool)
    """
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "datetime" in df.columns:
            df = df.set_index("datetime")
        else:
            raise ValueError("Data must have a DatetimeIndex or a 'datetime' column")
    df = df.sort_index()
    return df


def add_session_start(
    df: pd.DataFrame,
    session_open: str = "09:30",
    timezone: str = "America/New_York"
) -> pd.DataFrame:
    """
    Mark the first bar of each RTH session.
    Assumes the index is timezone-aware or will be localized.
    """
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize(timezone)
    else:
        df.index = df.index.tz_convert(timezone)

    times = df.index.strftime("%H:%M")
    df["session_start"] = times == session_open
    # Also mark the first bar of the day if session_open is missing (e.g. overnight data)
    df["session_start"] = df["session_start"] | (df.index.to_series().diff() > pd.Timedelta("6h"))
    return df


def make_continuous_ratio(
    front: pd.DataFrame,
    next_contract: pd.DataFrame,
    roll_date: pd.Timestamp
) -> pd.DataFrame:
    """
    Simple ratio-adjusted continuous series.
    This is a minimal example – production code needs a full roll calendar.
    """
    # Placeholder – real implementation will use a roll schedule
    raise NotImplementedError("Full continuous-contract builder coming next")
