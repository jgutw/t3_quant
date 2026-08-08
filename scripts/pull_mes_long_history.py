"""
Pull multi-year MES history and cache as 5-minute Parquet.

Databento has no native ohlcv-5m schema, so we pull ohlcv-1m in yearly
chunks, resample to 5m locally, and concatenate.

Usage:
  python scripts/pull_mes_long_history.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.bars import resample_ohlcv
from data.databento_loader import DATA_DIR, fetch_continuous


def _year_windows(start_year: int = 2019, end_year: int = 2026) -> list[tuple[str, str]]:
    """Half-open [start, end) windows; first starts at MES launch."""
    windows: list[tuple[str, str]] = []
    for y in range(start_year, end_year + 1):
        start = "2019-05-06" if y == 2019 else f"{y}-01-01"
        end = f"{y + 1}-01-01"
        windows.append((start, end))
    return windows


def main() -> None:
    print(f"Parquet dir: {DATA_DIR}")
    print("Pulling MES.v.0 ohlcv-1m by year, resampling to 5m ...")

    pieces: list[pd.DataFrame] = []
    for start, end in _year_windows():
        print(f"\n=== Chunk {start} -> {end} ===")
        try:
            df_1m = fetch_continuous(
                symbol="MES",
                start=start,
                end=end,
                schema="ohlcv-1m",
                roll="v",
                front=0,
                save=False,
            )
        except Exception as exc:
            print(f"Skipping chunk ({start} -> {end}): {exc}")
            continue

        if df_1m.empty:
            print("Empty chunk, skipping.")
            continue

        df_5m = resample_ohlcv(df_1m, "5min")
        print(f"  1m bars={len(df_1m):,} -> 5m bars={len(df_5m):,}")
        pieces.append(df_5m)

    if not pieces:
        raise SystemExit("No data downloaded.")

    out = pd.concat(pieces).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    fname = "MES_v0_ohlcv-5m_2019-05-06_latest.parquet"
    path = DATA_DIR / fname
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path)

    print(f"\nSaved -> {path}")
    print(f"Bars: {len(out):,} | {out.index.min()} -> {out.index.max()}")
    print(f"Session starts: {int(out['session_start'].sum())}")


if __name__ == "__main__":
    main()
