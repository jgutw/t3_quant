"""
Run the three SuperTrend-regime variants from the research spec.

  A) regime_only     — 15m ST regime, no pullback, no MTF
  B) regime_pullback — 15m ST + VWAP pullback, no MTF
  C) regime_full     — 15m ST + VWAP pullback + MTF >=75%

Usage:
  python -m backtest.run_regime_spec
"""

from __future__ import annotations

import logging
from typing import Any, Callable

import pandas as pd

from analytics.metrics import format_metrics_report, summarize_backtest
from backtest.engine import SimpleBacktester
from backtest.run_v1 import OUT_DIR, prepare_mes_5m
from risk.daily_risk_manager import DailyRiskManager
from strategies.supertrend_regime import SuperTrendRegimeStrategy
from strategies.weighted_ensemble import WeightedEnsembleStrategy

logging.getLogger("risk.daily_risk_manager").setLevel(logging.ERROR)


def _run(
    name: str,
    factory: Callable[[DailyRiskManager], Any],
    *,
    use_mtf_data: bool,
) -> dict[str, Any]:
    data, higher_tf, _ = prepare_mes_5m()
    risk = DailyRiskManager()
    strategy = factory(risk)
    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=6.0,
        slippage_ticks=1.0,
    )
    result = bt.run(
        data,
        higher_tf=higher_tf if use_mtf_data else None,
        cpr=None,
    )
    metrics = summarize_backtest(result)

    stem = f"regime_spec_{name}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = format_metrics_report(metrics, title=f"Regime spec — {name}")
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
    shape = {
        "equity_start": float(eq.iloc[0]) if len(eq) else 0.0,
        "equity_end": float(eq.iloc[-1]) if len(eq) else 0.0,
        "equity_min": float(eq.min()) if len(eq) else 0.0,
        "equity_max": float(eq.max()) if len(eq) else 0.0,
        "pct_bars_above_zero": float((eq > 0).mean()) if len(eq) else 0.0,
    }
    print(report)
    print(
        f"Equity shape: start={shape['equity_start']:.2f} end={shape['equity_end']:.2f} "
        f"min={shape['equity_min']:.2f} max={shape['equity_max']:.2f} "
        f"pct_above_0={shape['pct_bars_above_zero']:.1%}"
    )
    print()
    return {"name": name, "metrics": metrics, "result": result, "shape": shape}


def main() -> None:
    print("Preparing MES 5m once...\n")
    prepare_mes_5m()

    # Reference row: prior ensemble MTF baseline
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
                cooldown_bars=6,
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
                cooldown_bars=6,
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
                cooldown_bars=6,
                flatten_outside_window=True,
            ),
        ),
    ]

    rows = []
    for name, use_mtf_data, factory in variants:
        print(f"--- {name} ---")
        out = _run(name, factory, use_mtf_data=use_mtf_data)
        m, s = out["metrics"], out["shape"]
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
                "equity_min": s["equity_min"],
                "equity_max": s["equity_max"],
                "pct_bars_above_zero": s["pct_bars_above_zero"],
                "exit_reasons": m["exit_reasons"],
            }
        )

    summary = pd.DataFrame(rows)
    path = OUT_DIR / "regime_spec_summary.csv"
    summary.to_csv(path, index=False)

    show = summary[
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
            "pct_bars_above_zero",
        ]
    ].copy()
    show["final_pnl"] = show["final_pnl"].map(lambda x: f"${x:,.2f}")
    show["expectancy"] = show["expectancy"].map(lambda x: f"${x:,.2f}")
    show["worst_intraday"] = show["worst_intraday"].map(lambda x: f"${x:,.2f}")
    show["win_rate"] = show["win_rate"].map(lambda x: f"{x:.1%}")
    show["trades_per_day"] = show["trades_per_day"].map(lambda x: f"{x:.2f}")
    show["profit_factor"] = show["profit_factor"].map(
        lambda x: f"{x:.2f}" if x is not None else "n/a"
    )
    show["pct_bars_above_zero"] = show["pct_bars_above_zero"].map(lambda x: f"{x:.1%}")

    print("=== Spec variant summary ===")
    print(show.to_string(index=False))
    print(f"\nSaved -> {path}")
    print("Equity CSVs -> analytics/output/regime_spec_*_equity.csv")


if __name__ == "__main__":
    main()
