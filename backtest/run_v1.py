"""
V1 research runner: cached continuous MES -> 5m gated ensemble -> risk-aware backtest.

Baseline gates (toggleable):
  - Multi-TF permission (15m + 1h, >= 75% agreement)
  - Daily CPR (long above TC / short below BC)

Baseline gates (OFF for clean measurement):
  - ORB entry filter
  - Adaptive weight updates (equal-weight ensemble)

Usage (from repo root):
  python -m backtest.run_v1
  python -m backtest.run_v1_ablation
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

import pandas as pd

from analytics.metrics import format_metrics_report, summarize_backtest
from backtest.engine import SimpleBacktester
from data.bars import filter_rth, resample_ohlcv
from data.databento_loader import load_parquet
from data.continuous import add_session_start
from features.session_levels import cpr_levels_series
from risk.daily_risk_manager import DailyRiskManager
from strategies.weighted_ensemble import WeightedEnsembleStrategy

OUT_DIR = Path(__file__).resolve().parents[1] / "analytics" / "output"

# Module-level cache so ablation variants don't re-load / re-resample
_PREPARED: Optional[tuple[pd.DataFrame, dict[str, pd.Series], pd.DataFrame]] = None


def prepare_mes_5m(force: bool = False) -> tuple[pd.DataFrame, dict[str, pd.Series], pd.DataFrame]:
    global _PREPARED
    if _PREPARED is not None and not force:
        return _PREPARED

    raw = load_parquet("MES", schema="ohlcv-1m", roll="v", front=0)
    bars_5m = resample_ohlcv(raw, "5min")
    bars_5m = filter_rth(bars_5m)
    bars_5m = add_session_start(bars_5m)

    higher_tf = {
        "15m": resample_ohlcv(bars_5m, "15min")["close"],
        "1h": resample_ohlcv(bars_5m, "1h")["close"],
    }
    cpr = cpr_levels_series(bars_5m)
    _PREPARED = (bars_5m, higher_tf, cpr)
    return _PREPARED


def run_v1(
    stop_points: float = 6.0,
    slippage_ticks: float = 1.0,
    multi_tf_agreement: float = 0.75,
    use_mtf: bool = True,
    use_cpr: bool = True,
    tag: Optional[str] = None,
    save: bool = True,
    quiet: bool = False,
) -> dict[str, Any]:
    data, higher_tf, cpr = prepare_mes_5m()
    if not quiet:
        print(
            f"Bars: {len(data):,} | {data.index.min()} -> {data.index.max()} | "
            f"sessions~{int(data['session_start'].sum())}"
        )
        print(f"Gates: MTF={'ON' if use_mtf else 'OFF'} | CPR={'ON' if use_cpr else 'OFF'}")

    risk = DailyRiskManager()
    strategy = WeightedEnsembleStrategy(
        risk_manager=risk,
        use_adaptive_weights=False,  # equal-weight baseline
        min_accuracy=0.48,
        multi_tf_agreement=multi_tf_agreement,
        require_cpr_filter=use_cpr,
        require_orb_filter=False,
    )

    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=stop_points,
        slippage_ticks=slippage_ticks,
    )

    higher = higher_tf if use_mtf else None
    cpr_arg = cpr if use_cpr else None
    result = bt.run(data, higher_tf=higher, cpr=cpr_arg)
    metrics = summarize_backtest(result)

    gate_label = f"MTF={'ON' if use_mtf else 'OFF'} CPR={'ON' if use_cpr else 'OFF'}"
    stem = tag or (
        "v1_mes_5m_"
        + ("mtf_" if use_mtf else "nomtf_")
        + ("cpr" if use_cpr else "nocpr")
    )
    title = f"V1 MES 5m Ensemble ({gate_label}, equal weight)"

    if save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        trades_path = OUT_DIR / f"{stem}_trades.csv"
        equity_path = OUT_DIR / f"{stem}_equity.csv"
        metrics_path = OUT_DIR / f"{stem}_metrics.txt"

        if result.trades:
            pd.DataFrame(
                [
                    {
                        "symbol": t.symbol,
                        "entry_time": t.entry_time,
                        "exit_time": t.exit_time,
                        "qty": t.qty,
                        "entry_price": t.entry_price,
                        "exit_price": t.exit_price,
                        "pnl": t.pnl,
                        "reason": t.reason,
                    }
                    for t in result.trades
                ]
            ).to_csv(trades_path, index=False)
        else:
            pd.DataFrame().to_csv(trades_path, index=False)

        result.equity_curve.to_csv(equity_path, header=["equity"])
        report = format_metrics_report(metrics, title=title)
        metrics_path.write_text(report + "\n", encoding="utf-8")
        if not quiet:
            print(report)
            print(f"\nSaved -> {OUT_DIR} ({stem}_*)")
    elif not quiet:
        print(format_metrics_report(metrics, title=title))

    return {
        "result": result,
        "metrics": metrics,
        "use_mtf": use_mtf,
        "use_cpr": use_cpr,
        "tag": stem,
        "title": title,
    }


if __name__ == "__main__":
    run_v1()
