"""
Option A: SuperTrend regime on 15-minute MES (research sample).

Resamples the existing 1m cache → 15m RTH, then runs the same three
regime variants with stops/cooldown scaled for the slower bar.

Usage:
  python -m backtest.run_regime_15m
"""

from __future__ import annotations

import logging
from typing import Any, Callable, Optional

import pandas as pd

from analytics.metrics import format_metrics_report, summarize_backtest
from backtest.engine import SimpleBacktester
from backtest.run_v1 import OUT_DIR
from data.bars import filter_rth, resample_ohlcv
from data.continuous import add_session_start
from data.databento_loader import load_parquet
from risk.daily_risk_manager import DailyRiskManager
from strategies.supertrend_regime import SuperTrendRegimeStrategy
from strategies.weighted_ensemble import WeightedEnsembleStrategy

logging.getLogger("risk.daily_risk_manager").setLevel(logging.ERROR)

_PREPARED_15M: Optional[tuple[pd.DataFrame, dict[str, pd.Series]]] = None


def prepare_mes_15m(force: bool = False) -> tuple[pd.DataFrame, dict[str, pd.Series]]:
    global _PREPARED_15M
    if _PREPARED_15M is not None and not force:
        return _PREPARED_15M

    raw = load_parquet("MES", schema="ohlcv-1m", roll="v", front=0)
    bars = resample_ohlcv(raw, "15min")
    bars = filter_rth(bars)
    bars = add_session_start(bars)

    higher_tf = {
        "1h": resample_ohlcv(bars, "1h")["close"],
        "1d": resample_ohlcv(bars, "1D")["close"],
    }
    _PREPARED_15M = (bars, higher_tf)
    return _PREPARED_15M


def _run(
    name: str,
    factory: Callable[[DailyRiskManager], Any],
    *,
    use_mtf_data: bool,
    stop_points: float,
) -> dict[str, Any]:
    data, higher_tf = prepare_mes_15m()
    risk = DailyRiskManager()
    strategy = factory(risk)
    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=stop_points,
        slippage_ticks=1.0,
    )
    result = bt.run(
        data,
        higher_tf=higher_tf if use_mtf_data else None,
        cpr=None,
    )
    metrics = summarize_backtest(result)
    stem = f"regime_15m_{name}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = format_metrics_report(metrics, title=f"15m regime — {name}")
    (OUT_DIR / f"{stem}_metrics.txt").write_text(report + "\n", encoding="utf-8")
    result.equity_curve.to_csv(OUT_DIR / f"{stem}_equity.csv", header=["equity"])
    if result.trades:
        pd.DataFrame(
            [
                {
                    "entry_time": t.entry_time,
                    "exit_time": t.exit_time,
                    "qty": t.qty,
                    "pnl": t.pnl,
                    "reason": t.reason,
                }
                for t in result.trades
            ]
        ).to_csv(OUT_DIR / f"{stem}_trades.csv", index=False)

    eq = result.equity_curve
    print(report)
    if len(eq):
        print(
            f"Equity shape: end={eq.iloc[-1]:.2f} min={eq.min():.2f} "
            f"max={eq.max():.2f} pct>0={(eq > 0).mean():.1%}"
        )
    print()
    return {"name": name, "metrics": metrics, "result": result}


def main() -> None:
    print("Preparing MES 15m RTH from cached 1m...\n")
    data, _ = prepare_mes_15m()
    print(
        f"Bars: {len(data):,} | {data.index.min()} -> {data.index.max()} | "
        f"sessions~{int(data['session_start'].sum())}\n"
    )

    # Wider stop + shorter cooldown (in bars) for 15m primary
    stop = 10.0
    cooldown = 2  # 30 minutes

    variants = [
        (
            "ensemble_mtf_ref",
            True,
            lambda risk: WeightedEnsembleStrategy(
                risk_manager=risk,
                use_adaptive_weights=False,
                require_cpr_filter=False,
                require_orb_filter=False,
                multi_tf_agreement=0.75,
            ),
        ),
        (
            "regime_only",
            False,
            lambda risk: SuperTrendRegimeStrategy(
                risk_manager=risk,
                require_pullback=False,
                use_mtf=False,
                min_regime_bars=3,
                entry_window_start="10:00",
                entry_window_end="11:30",
                cooldown_bars=cooldown,
                flatten_outside_window=True,
            ),
        ),
        (
            "regime_pullback",
            False,
            lambda risk: SuperTrendRegimeStrategy(
                risk_manager=risk,
                require_pullback=True,
                use_mtf=False,
                min_regime_bars=3,
                entry_window_start="10:00",
                entry_window_end="11:30",
                cooldown_bars=cooldown,
                flatten_outside_window=True,
            ),
        ),
        (
            "regime_full",
            True,
            lambda risk: SuperTrendRegimeStrategy(
                risk_manager=risk,
                require_pullback=True,
                use_mtf=True,
                multi_tf_agreement=0.75,
                min_regime_bars=3,
                entry_window_start="10:00",
                entry_window_end="11:30",
                cooldown_bars=cooldown,
                flatten_outside_window=True,
            ),
        ),
    ]

    rows = []
    for name, use_mtf_data, factory in variants:
        print(f"--- {name} (stop={stop}) ---")
        out = _run(name, factory, use_mtf_data=use_mtf_data, stop_points=stop)
        m = out["metrics"]
        rows.append(
            {
                "variant": name,
                "final_pnl": m["final_pnl"],
                "profit_factor": m["profit_factor"],
                "expectancy": m["expectancy_per_trade"],
                "win_rate": m["win_rate"],
                "trades_per_day": m["trades_per_day"],
                "trades": m["num_trades"],
                "worst_intraday": m["worst_intraday_pnl"],
                "max_dd": m["max_drawdown"],
                "locked_days": m["locked_out_days"],
                "commission": m["total_commission"],
            }
        )

    summary = pd.DataFrame(rows)
    path = OUT_DIR / "regime_15m_summary.csv"
    summary.to_csv(path, index=False)

    show = summary.copy()
    show["final_pnl"] = show["final_pnl"].map(lambda x: f"${x:,.2f}")
    show["expectancy"] = show["expectancy"].map(lambda x: f"${x:,.2f}")
    show["worst_intraday"] = show["worst_intraday"].map(lambda x: f"${x:,.2f}")
    show["win_rate"] = show["win_rate"].map(lambda x: f"{x:.1%}")
    show["trades_per_day"] = show["trades_per_day"].map(lambda x: f"{x:.2f}")
    show["profit_factor"] = show["profit_factor"].map(
        lambda x: f"{x:.2f}" if x is not None else "n/a"
    )
    show["commission"] = show["commission"].map(lambda x: f"${x:,.2f}")

    print("=== 15m regime summary ===")
    print(
        show[
            [
                "variant",
                "final_pnl",
                "profit_factor",
                "expectancy",
                "win_rate",
                "trades_per_day",
                "trades",
                "worst_intraday",
                "locked_days",
                "commission",
            ]
        ].to_string(index=False)
    )
    print(f"\nSaved -> {path}")


if __name__ == "__main__":
    main()
