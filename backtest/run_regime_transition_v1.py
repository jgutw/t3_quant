"""
regime_transition_v1 — Lightweight regime-transition fade on MES.

Usage (from repo root):
  python -m backtest.run_regime_transition_v1
"""

from __future__ import annotations

from datetime import time as dt_time
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.metrics import format_metrics_report, summarize_backtest
from backtest.engine import SimpleBacktester
from data.bars import filter_rth
from data.continuous import add_session_start
from data.databento_loader import DATA_DIR, load_parquet
from risk.daily_risk_manager import DailyRiskManager
from strategies.regime_transition import RegimeTransitionFade

OUT_DIR = Path(__file__).resolve().parents[1] / "analytics" / "output"
STEM = "regime_transition_v1"
N_TRIALS = 1


def load_mes_rth() -> pd.DataFrame:
    long_5m = sorted(DATA_DIR.glob("MES_v0_ohlcv-5m_*.parquet"))
    if long_5m:
        path = long_5m[-1]
        print(f"Loading {path.name} (longest available)")
        raw = pd.read_parquet(path)
    else:
        raw = load_parquet("MES", schema="ohlcv-1m", roll="v", front=0)
        from data.bars import resample_ohlcv

        raw = resample_ohlcv(raw, "5min")

    if raw.index.tz is None:
        raw = raw.copy()
        raw.index = raw.index.tz_localize("America/New_York")

    bars = filter_rth(raw)
    bars = add_session_start(bars)
    return bars


def _avg_hold_minutes(trades) -> float:
    if not trades:
        return 0.0
    mins = []
    for t in trades:
        if t.entry_time is None or t.exit_time is None:
            continue
        mins.append((t.exit_time - t.entry_time).total_seconds() / 60.0)
    return float(sum(mins) / len(mins)) if mins else 0.0


def _verdict(metrics: dict[str, Any], n_trades: int, worst: float) -> str:
    pf = metrics.get("profit_factor")
    dpf = metrics.get("deflated_profit_factor")
    dsr = metrics.get("deflated_sharpe")
    exp = metrics.get("expectancy_per_trade", 0.0)

    if worst < -750.0 - 1e-6:
        return "FAILED (hard-limit breach - risk bug)"

    if n_trades < 30:
        return "INCONCLUSIVE (< 30 trades)"

    if pf is None or pf <= 1.0:
        return "FAILED (raw PF <= 1.0 after costs)"

    deflated_ok = False
    if dpf is not None and dpf > 1.0:
        deflated_ok = True
    elif dsr is not None and dsr > 0:
        deflated_ok = True
    if not deflated_ok:
        return "FAILED (deflated metric <= 0 / deflated PF <= 1.0)"

    if exp <= 0:
        return "FAILED (non-positive expectancy)"

    if pf > 1.2 and deflated_ok and n_trades >= 30 and worst >= -750.0 and exp > 0:
        return "PASSED"

    return "FAILED (success criteria not all met)"


def run_regime_transition_v1(save: bool = True) -> dict[str, Any]:
    data = load_mes_rth()
    n_sessions = int(data["session_start"].sum())
    print(
        f"Bars: {len(data):,} | {data.index.min()} -> {data.index.max()} | "
        f"RTH sessions={n_sessions}"
    )

    risk = DailyRiskManager()
    strategy = RegimeTransitionFade(risk_manager=risk)

    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=8.0,
        slippage_ticks=1.0,
        bracket_hold=True,
        session_flatten_time=dt_time(15, 55),
        entry_on_open=True,
        max_hold_bars=strategy.H,
        allow_intrasession_reentry=True,
    )

    result = bt.run(data)
    metrics = summarize_backtest(result, n_trials=N_TRIALS)

    trade_days = {
        t.entry_time.date() for t in result.trades if t.entry_time is not None
    }
    frac_days = len(trade_days) / max(n_sessions, 1)
    avg_hold = _avg_hold_minutes(result.trades)
    metrics["fraction_days_with_trade"] = float(frac_days)
    metrics["avg_holding_minutes"] = float(avg_hold)
    metrics["n_trials"] = N_TRIALS

    verdict = _verdict(
        metrics,
        n_trades=int(result.num_trades),
        worst=float(result.worst_intraday_pnl),
    )

    pf = metrics.get("profit_factor")
    dpf = metrics.get("deflated_profit_factor")
    dsr = metrics.get("deflated_sharpe")
    lines = [
        "=== regime_transition_v1 - Lightweight Regime-Transition Fade (MES) ===",
        f"Sample:               {data.index.min()} -> {data.index.max()}",
        f"RTH sessions:         {n_sessions}",
        f"Number of trades:     {metrics['num_trades']}",
        f"Trades per day:       {metrics['trades_per_day']:.3f}",
        f"Win rate:             {metrics['win_rate']:.1%}",
        f"Avg win / avg loss:   ${metrics['avg_win']:,.2f} / ${metrics['avg_loss']:,.2f}",
        f"Expectancy / trade:   ${metrics['expectancy_per_trade']:,.2f}",
        f"Profit factor (raw):  {pf:.3f}" if pf is not None else "Profit factor (raw):  n/a",
        f"Deflated PF:          {dpf:.3f}" if dpf is not None else "Deflated PF:          n/a",
        f"Deflated Sharpe:      {dsr:.4f}" if dsr is not None else "Deflated Sharpe:      n/a",
        f"DSR probability:      {metrics.get('deflated_sharpe_prob', float('nan')):.3f}",
        f"n_trials:             {N_TRIALS}",
        f"Max drawdown:         ${metrics['max_drawdown']:,.2f}",
        f"Worst intraday:       ${metrics['worst_intraday_pnl']:,.2f}",
        f"Locked-out days:      {metrics['locked_out_days']}",
        f"Frac days w/ trade:   {frac_days:.1%}",
        f"Avg holding (min):    {avg_hold:.1f}",
        f"Final PnL:            ${metrics['final_pnl']:,.2f}",
        f"Exit reasons:         {metrics['exit_reasons']}",
        "",
        f"VERDICT: {verdict}",
    ]
    report = "\n".join(lines)
    print(report)

    if save:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        trades_path = OUT_DIR / f"{STEM}_trades.csv"
        equity_path = OUT_DIR / f"{STEM}_equity.csv"
        metrics_path = OUT_DIR / f"{STEM}_metrics.txt"

        if result.trades:
            pd.DataFrame(
                [
                    {
                        "symbol": t.symbol,
                        "entry_time": t.entry_time,
                        "exit_time": t.exit_time,
                        "direction": int(1 if t.qty > 0 else -1),
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
        metrics_path.write_text(
            report + "\n\n" + format_metrics_report(metrics, title=STEM) + "\n",
            encoding="utf-8",
        )
        print(f"\nSaved -> {OUT_DIR} ({STEM}_*)")

    return {
        "result": result,
        "metrics": metrics,
        "verdict": verdict,
        "tag": STEM,
    }


if __name__ == "__main__":
    run_regime_transition_v1()
