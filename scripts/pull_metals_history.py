"""
Pull multi-year MGC / SIL continuous history and cache as 5-minute Parquet.

Same pattern as pull_mes_long_history.py: Databento ohlcv-1m by year,
resample to 5m locally, concatenate.

Usage:
  python scripts/pull_metals_history.py
  python scripts/pull_metals_history.py --symbols MGC
  python scripts/pull_metals_history.py --symbols MGC SIL --start-year 2020
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from data.bars import resample_ohlcv
from data.databento_loader import DATA_DIR, fetch_continuous


def _year_windows(start_year: int, end_year: int) -> list[tuple[str, str]]:
    windows: list[tuple[str, str]] = []
    for y in range(start_year, end_year + 1):
        start = f"{y}-01-01"
        end = f"{y + 1}-01-01"
        windows.append((start, end))
    return windows


def pull_symbol(symbol: str, start_year: int, end_year: int) -> Path:
    print(f"\n########## {symbol} ##########")
    print(f"Pulling {symbol}.v.0 ohlcv-1m by year, resampling to 5m ...")

    pieces: list[pd.DataFrame] = []
    for start, end in _year_windows(start_year, end_year):
        print(f"\n=== {symbol} chunk {start} -> {end} ===")
        try:
            df_1m = fetch_continuous(
                symbol=symbol,
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

        if df_1m is None or df_1m.empty:
            print("Empty chunk, skipping.")
            continue

        df_5m = resample_ohlcv(df_1m, "5min")
        print(f"  1m bars={len(df_1m):,} -> 5m bars={len(df_5m):,}")
        pieces.append(df_5m)

    if not pieces:
        raise RuntimeError(f"No data downloaded for {symbol}.")

    out = pd.concat(pieces).sort_index()
    out = out[~out.index.duplicated(keep="last")]
    fname = f"{symbol}_v0_ohlcv-5m_{start_year}-01-01_latest.parquet"
    path = DATA_DIR / fname
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    out.to_parquet(path)

    print(f"\nSaved -> {path}")
    print(f"Bars: {len(out):,} | {out.index.min()} -> {out.index.max()}")
    if "session_start" in out.columns:
        print(f"Session starts: {int(out['session_start'].sum())}")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Pull MGC/SIL continuous 5m history")
    parser.add_argument(
        "--symbols",
        nargs="+",
        default=["MGC", "SIL"],
        help="Root symbols to pull (default: MGC SIL)",
    )
    parser.add_argument("--start-year", type=int, default=2020)
    parser.add_argument("--end-year", type=int, default=2026)
    args = parser.parse_args()

    print(f"Parquet dir: {DATA_DIR}")
    saved: list[Path] = []
    for sym in args.symbols:
        try:
            saved.append(pull_symbol(sym.upper(), args.start_year, args.end_year))
        except Exception as exc:
            print(f"FAILED {sym}: {exc}")

    if not saved:
        raise SystemExit("No metals data saved.")
    print("\n=== Done ===")
    for p in saved:
        print(f"  {p.name}")


if __name__ == "__main__":
    main()
