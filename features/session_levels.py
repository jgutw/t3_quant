"""
Session-level reference series: daily CPR (and helpers) aligned to bar index.
"""

from __future__ import annotations

import pandas as pd

from features.indicators import central_pivot_range


def cpr_levels_series(df: pd.DataFrame) -> pd.DataFrame:
    """
    For each bar, attach the prior calendar day's CPR levels.

    Uses prior day's high / low / close (full available session in `df`).
    First trading day in the sample has NaN levels (no prior day).
    """
    if df.empty:
        return pd.DataFrame(columns=["pivot", "bc", "tc", "r1", "s1"], index=df.index)

    daily = (
        df.groupby(df.index.date)
        .agg(high=("high", "max"), low=("low", "min"), close=("close", "last"))
        .sort_index()
    )
    prev = daily.shift(1)

    rows = []
    for d, row in prev.iterrows():
        if pd.isna(row["close"]) or pd.isna(row["high"]) or pd.isna(row["low"]):
            continue
        levels = central_pivot_range(float(row["high"]), float(row["low"]), float(row["close"]))
        levels["date"] = d
        rows.append(levels)

    if not rows:
        return pd.DataFrame(
            index=df.index, columns=["pivot", "bc", "tc", "r1", "s1"], dtype=float
        )

    cpr_daily = pd.DataFrame(rows).set_index("date")
    mapped = cpr_daily.reindex(pd.Index(df.index.date))
    mapped.index = df.index
    return mapped[["pivot", "bc", "tc", "r1", "s1"]]
