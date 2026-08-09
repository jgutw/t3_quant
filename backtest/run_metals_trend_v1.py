"""
Kurth large-tick test: existing SuperTrend-regime / ensemble on MGC and SIL.

Same DailyRiskManager, same deflated metrics, optional NY-hours (RTH) filter.
No new indicators. Single pre-specified variant set per symbol.

Usage:
  python -m backtest.run_metals_trend_v1
  python -m backtest.run_metals_trend_v1 --symbols MGC
  python -m backtest.run_metals_trend_v1 --no-rth
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path
from typing import Any, Callable, Optional

import pandas as pd

from analytics.metrics import format_metrics_report, summarize_backtest
from backtest.engine import SimpleBacktester
from data.bars import filter_rth, resample_ohlcv
from data.continuous import add_session_start
from data.databento_loader import DATA_DIR
from risk.daily_risk_manager import DailyRiskManager
from strategies.supertrend_regime import SuperTrendRegimeStrategy
from strategies.weighted_ensemble import WeightedEnsembleStrategy

logging.getLogger("risk.daily_risk_manager").setLevel(logging.ERROR)

OUT_DIR = Path(__file__).resolve().parents[1] / "analytics" / "output"

# Dollar-risk-matched stops vs MES stop≈6pt ($30): MGC $10/pt → 3pt; SIL $1000/pt → 0.03
STOP_POINTS = {"MGC": 3.0, "SIL": 0.03}


def load_metal_5m(symbol: str, use_rth: bool = True) -> pd.DataFrame:
    files = sorted(DATA_DIR.glob(f"{symbol}_v0_ohlcv-5m_*.parquet"))
    if not files:
        raise FileNotFoundError(
            f"No {symbol} 5m Parquet in {DATA_DIR}. "
            f"Run: python scripts/pull_metals_history.py --symbols {symbol}"
        )
    path = files[-1]
    print(f"Loading {path.name}")
    raw = pd.read_parquet(path)
    if raw.index.tz is None:
        raw = raw.copy()
        raw.index = raw.index.tz_localize("America/New_York")
    bars = filter_rth(raw) if use_rth else raw.copy()
    return add_session_start(bars)


def _variants(cooldown: int = 3) -> list[tuple[str, bool, Callable[[DailyRiskManager], Any]]]:
    return [
        (
            "ensemble_mtf",
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


def _verdict(metrics: dict[str, Any]) -> str:
    pf = metrics.get("profit_factor")
    dsr = metrics.get("deflated_sharpe")
    dpf = metrics.get("deflated_profit_factor")
    n = int(metrics.get("num_trades", 0))
    worst = float(metrics.get("worst_intraday_pnl", 0.0))
    exp = float(metrics.get("expectancy_per_trade", 0.0))

    if worst < -750.0 - 1e-6:
        return "FAILED (hard-limit breach)"
    if n < 30:
        return "INCONCLUSIVE (<30 trades)"
    if pf is None or pf <= 1.0:
        return "FAILED (raw PF <= 1.0)"
    deflated_ok = (dpf is not None and dpf > 1.0) or (dsr is not None and dsr > 0)
    if not deflated_ok:
        return "FAILED (deflated not constructive)"
    if exp <= 0:
        return "FAILED (non-positive expectancy)"
    if pf > 1.2 and deflated_ok:
        return "PASSED"
    return "FAILED (success criteria not all met)"


def run_symbol(symbol: str, use_rth: bool = True) -> pd.DataFrame:
    data = load_metal_5m(symbol, use_rth=use_rth)
    higher_tf = {
        "15m": resample_ohlcv(data, "15min")["close"],
        "1h": resample_ohlcv(data, "1h")["close"],
    }
    stop = STOP_POINTS[symbol]
    variants = _variants()
    n_trials = len(variants)

    print(
        f"\n=== {symbol} | bars={len(data):,} | {data.index.min()} -> {data.index.max()} | "
        f"sessions~{int(data['session_start'].sum())} | RTH={use_rth} | stop={stop} | N={n_trials} ===\n"
    )

    rows = []
    for name, use_mtf, factory in variants:
        risk = DailyRiskManager()
        strategy = factory(risk)
        bt = SimpleBacktester(
            strategy=strategy,
            risk_manager=risk,
            symbol=symbol,
            stop_points=stop,
            slippage_ticks=1.0,
        )
        result = bt.run(
            data,
            higher_tf=higher_tf if use_mtf else None,
            cpr=None,
        )
        metrics = summarize_backtest(result, n_trials=n_trials)
        verdict = _verdict(metrics)
        stem = f"metals_trend_v1_{symbol}_{name}"
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        report = format_metrics_report(
            metrics, title=f"metals_trend_v1 {symbol} — {name}"
        )
        (OUT_DIR / f"{stem}_metrics.txt").write_text(
            report + f"\nVERDICT: {verdict}\n", encoding="utf-8"
        )
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

        pf = metrics.get("profit_factor")
        dsr = metrics.get("deflated_sharpe")
        print(
            f"{name:16s}  trades={metrics['num_trades']:5d}  "
            f"PF={pf if pf is not None else float('nan'):.3f}  "
            f"DSR={dsr if dsr is not None else float('nan'):.3f}  "
            f"E[x]={metrics['expectancy_per_trade']:.2f}  "
            f"worst={metrics['worst_intraday_pnl']:.2f}  "
            f"{verdict}"
        )
        rows.append(
            {
                "symbol": symbol,
                "variant": name,
                "rth": use_rth,
                "stop_points": stop,
                "n_trials": n_trials,
                "num_trades": metrics["num_trades"],
                "trades_per_day": metrics["trades_per_day"],
                "win_rate": metrics["win_rate"],
                "expectancy": metrics["expectancy_per_trade"],
                "profit_factor": metrics["profit_factor"],
                "deflated_pf": metrics.get("deflated_profit_factor"),
                "deflated_sharpe": metrics.get("deflated_sharpe"),
                "final_pnl": metrics["final_pnl"],
                "max_dd": metrics["max_drawdown"],
                "worst_intraday": metrics["worst_intraday_pnl"],
                "locked_days": metrics["locked_out_days"],
                "verdict": verdict,
            }
        )

    return pd.DataFrame(rows)


def main(symbols: Optional[list[str]] = None, use_rth: bool = True) -> None:
    symbols = symbols or ["MGC", "SIL"]
    frames = []
    for sym in symbols:
        try:
            frames.append(run_symbol(sym.upper(), use_rth=use_rth))
        except FileNotFoundError as exc:
            print(f"SKIP {sym}: {exc}")
        except Exception as exc:
            print(f"FAILED {sym}: {exc}")
            raise

    if not frames:
        raise SystemExit("No metals results. Pull data first.")

    summary = pd.concat(frames, ignore_index=True)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / "metals_trend_v1_summary.csv"
    summary.to_csv(path, index=False)

    print("\n=== metals_trend_v1 summary (Kurth large-tick test) ===")
    show = summary.copy()
    for col in ("expectancy", "final_pnl", "worst_intraday", "max_dd"):
        show[col] = show[col].map(lambda x: f"${x:,.2f}")
    show["win_rate"] = show["win_rate"].map(lambda x: f"{x:.1%}")
    show["profit_factor"] = show["profit_factor"].map(
        lambda x: f"{x:.3f}" if x is not None else "n/a"
    )
    show["deflated_sharpe"] = show["deflated_sharpe"].map(
        lambda x: f"{x:.3f}" if x is not None and pd.notna(x) else "n/a"
    )
    print(
        show[
            [
                "symbol",
                "variant",
                "num_trades",
                "profit_factor",
                "deflated_sharpe",
                "expectancy",
                "worst_intraday",
                "verdict",
            ]
        ].to_string(index=False)
    )
    print(f"\nSaved -> {path}")

    any_pass = (summary["verdict"] == "PASSED").any()
    print(
        "\nKURTH TEST READOUT: "
        + (
            "at least one metals variant PASSED - large-tick channel supported"
            if any_pass
            else "no metals variant PASSED - short-horizon OHLCV trend not rescued by tick-size alone under our constraints"
        )
    )


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbols", nargs="+", default=["MGC", "SIL"])
    ap.add_argument(
        "--no-rth",
        action="store_true",
        help="Use full continuous session (no 09:30-16:00 NY filter)",
    )
    args = ap.parse_args()
    main(symbols=args.symbols, use_rth=not args.no_rth)
