"""
Databento continuous-contract loader for t3_quant.
Pulls MES / MGC / SIL continuous contracts and saves clean Parquet files
with the session_start column expected by the rest of the system.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Literal
from datetime import datetime, date

import pandas as pd
import databento as db
from dotenv import load_dotenv

from data.continuous import add_session_start

load_dotenv()  # reads .env

# Default location for cached Parquet files
DATA_DIR = Path(__file__).resolve().parent / "parquet"
DATA_DIR.mkdir(exist_ok=True)


def get_client() -> db.Historical:
    key = os.getenv("DATABENTO_API_KEY")
    if not key:
        raise ValueError("DATABENTO_API_KEY not found in environment or .env")
    return db.Historical(key)


def fetch_continuous(
    symbol: str = "MES",
    start: str | date | datetime = "2024-01-01",
    end: Optional[str | date | datetime] = None,
    schema: Literal["ohlcv-1s", "ohlcv-1m", "ohlcv-1h", "ohlcv-1d"] = "ohlcv-1m",
    roll: Literal["v", "n"] = "v",          # volume or open-interest
    front: int = 0,                         # 0 = front month
    save: bool = True,
) -> pd.DataFrame:
    """
    Fetch continuous contract data from Databento.

    Parameters
    ----------
    symbol : str
        Root symbol (MES, ES, MGC, SIL, ...)
    start, end : date-like
        Inclusive range. end=None → today
    schema : str
        Bar size
    roll : "v" | "n"
        Volume-based or open-interest-based continuous
    front : int
        0 = front month, 1 = second month, etc.
    save : bool
        Write Parquet to data/parquet/
    """
    client = get_client()

    continuous_symbol = f"{symbol}.{roll}.{front}"
    print(f"Requesting {continuous_symbol} | {schema} | {start} -> {end or 'now'}")

    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        symbols=continuous_symbol,
        stype_in="continuous",
        schema=schema,
        start=start,
        end=end,
    )

    df = data.to_df()

    # Standardize column names and index
    if not isinstance(df.index, pd.DatetimeIndex):
        if "ts_event" in df.columns:
            df = df.set_index("ts_event")
        else:
            df.index = pd.to_datetime(df.index)

    df = df.sort_index()

    # Keep only the columns we need + rename if necessary
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].copy()

    # Add session_start flag (RTH 09:30 ET)
    df = add_session_start(df)

    if save:
        fname = f"{symbol}_{roll}{front}_{schema}_{start}_{end or 'latest'}.parquet"
        fname = fname.replace(":", "-").replace(" ", "_")
        path = DATA_DIR / fname
        df.to_parquet(path)
        print(f"Saved -> {path}  ({len(df):,} rows)")

    return df


def load_parquet(
    symbol: str = "MES",
    schema: str = "ohlcv-1m",
    roll: str = "v",
    front: int = 0,
) -> pd.DataFrame:
    """
    Load the most recent matching Parquet file for convenience.
    """
    pattern = f"{symbol}_{roll}{front}_{schema}_*.parquet"
    files = sorted(DATA_DIR.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No Parquet found matching {pattern}")
    path = files[-1]
    print(f"Loading {path.name}")
    return pd.read_parquet(path)


# ------------------------------------------------------------------
# Quick CLI-style usage when run directly
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Example: last ~6 months of 1-minute continuous MES
    df = fetch_continuous(
        symbol="MES",
        start="2025-02-01",
        end="2025-08-01",
        schema="ohlcv-1m",
        roll="v",
        front=0,
        save=True,
    )
    print(df.tail())
    print(f"\nSession starts found: {df['session_start'].sum()}")
