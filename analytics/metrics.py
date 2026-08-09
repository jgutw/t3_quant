"""
Backtest metrics for V1 research reports.

Includes optional Deflated Sharpe / deflated PF and multi-variant PBO
(Bailey & López de Prado methodology — see analytics/deflated.py).
"""

from __future__ import annotations

from typing import Any, Dict, List, Mapping, Optional

import numpy as np
import pandas as pd

from analytics.deflated import (
    DeflatedSharpeResult,
    deflated_profit_factor,
    deflated_sharpe,
    equity_to_returns,
    probability_backtest_overfitting,
)
from backtest.engine import BacktestResult, Trade


def _daily_pnl_from_result(result: BacktestResult) -> pd.Series:
    """Prefer equity diffs; fall back to trade PnL by exit date."""
    if len(result.equity_curve):
        eq = result.equity_curve.astype(float)
        # Collapse to daily last equity then diff
        daily_eq = eq.groupby(eq.index.date).last()
        daily_eq.index = pd.to_datetime(list(daily_eq.index))
        return daily_eq.diff().dropna()

    trades: List[Trade] = result.trades
    if not trades:
        return pd.Series(dtype=float)
    rows = []
    for t in trades:
        if t.exit_time is None:
            continue
        rows.append((pd.Timestamp(t.exit_time).normalize(), float(t.pnl)))
    if not rows:
        return pd.Series(dtype=float)
    df = pd.DataFrame(rows, columns=["day", "pnl"])
    return df.groupby("day")["pnl"].sum().sort_index()


def summarize_backtest(
    result: BacktestResult,
    n_trials: Optional[int] = None,
    sr_benchmark: float = 0.0,
) -> Dict[str, Any]:
    """
    Summarise a single backtest.

    When `n_trials` is provided (multi-variant / ablation context), also report
    raw Sharpe, Deflated Sharpe (z and probability), and a haircut PF.
    """
    trades: List[Trade] = result.trades
    pnls = np.array([t.pnl for t in trades], dtype=float) if trades else np.array([])

    n = len(pnls)
    wins = pnls[pnls > 0] if n else np.array([])
    losses = pnls[pnls <= 0] if n else np.array([])

    if len(result.equity_curve):
        days = pd.Index(result.equity_curve.index.date).unique()
        n_days = max(len(days), 1)
    elif trades:
        days = pd.Index([t.exit_time.date() for t in trades if t.exit_time is not None]).unique()
        n_days = max(len(days), 1)
    else:
        n_days = 1

    gross_profit = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    win_rate = float(len(wins) / n) if n else 0.0
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    expectancy = float(pnls.mean()) if n else 0.0
    profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float("inf") if gross_profit > 0 else 0.0
    pf_out: Optional[float] = float(profit_factor) if np.isfinite(profit_factor) else None

    reasons: Dict[str, int] = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1

    worst = getattr(result, "worst_intraday_pnl", None)
    if worst is None:
        worst = getattr(result, "worst_intraday", 0.0)

    daily = _daily_pnl_from_result(result)
    raw_sharpe = 0.0
    if len(daily) >= 2 and float(daily.std(ddof=1)) > 0:
        raw_sharpe = float(daily.mean() / daily.std(ddof=1) * np.sqrt(252.0))

    out: Dict[str, Any] = {
        "final_pnl": float(result.final_pnl),
        "max_drawdown": float(result.max_dd),
        "worst_intraday_pnl": float(worst),
        "total_commission": float(getattr(result, "total_commission", 0.0)),
        "num_trades": int(result.num_trades),
        "locked_out_days": int(result.locked_out_days),
        "trading_days": int(n_days),
        "trades_per_day": float(n / n_days),
        "win_rate": win_rate,
        "expectancy_per_trade": expectancy,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "profit_factor": pf_out,
        "sharpe": raw_sharpe,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "exit_reasons": reasons,
        "n_trials": int(n_trials) if n_trials is not None else None,
    }

    if n_trials is not None and len(daily) >= 3:
        # Non-annualised series into DSR (matches Bailey setup on the observation frequency)
        dsr_res: DeflatedSharpeResult = deflated_sharpe(
            daily,
            n_trials=int(n_trials),
            sr_benchmark=sr_benchmark,
            periods_per_year=None,
        )
        out.update(
            {
                "sharpe_non_annualised": dsr_res.sharpe,
                "sr0_null_max": dsr_res.sr0,
                "deflated_sharpe": dsr_res.dsr,
                "deflated_sharpe_prob": dsr_res.dsr_prob,
                "probabilistic_sharpe": dsr_res.psr,
                "deflated_profit_factor": deflated_profit_factor(pf_out, dsr_res.dsr_prob),
                "returns_skew": dsr_res.skew,
                "returns_kurtosis": dsr_res.kurtosis,
            }
        )

    return out


def summarize_multi_variant(
    variant_results: Mapping[str, BacktestResult],
    n_trials: Optional[int] = None,
    n_blocks: int = 16,
    compute_pbo: bool = True,
) -> Dict[str, Any]:
    """
    Summarise an ablation / regime grid.

    Records N (defaults to number of variants), per-variant raw + deflated
    metrics, and optional CSCV PBO across aligned daily equity returns.
    """
    names = list(variant_results.keys())
    n = int(n_trials) if n_trials is not None else len(names)

    per_variant: Dict[str, Dict[str, Any]] = {}
    returns_map: Dict[str, pd.Series] = {}
    for name, res in variant_results.items():
        per_variant[name] = summarize_backtest(res, n_trials=n)
        daily = _daily_pnl_from_result(res)
        if len(daily):
            returns_map[name] = daily

    # Align for PBO
    pbo: Optional[float] = None
    if compute_pbo and len(returns_map) >= 2:
        # Reindex to union, fill missing with 0 (no activity that day)
        idx = None
        for s in returns_map.values():
            idx = s.index if idx is None else idx.union(s.index)
        aligned = {k: v.reindex(idx).fillna(0.0) for k, v in returns_map.items()}
        pbo = probability_backtest_overfitting(aligned, n_blocks=n_blocks)

    return {
        "n_trials": n,
        "variants": per_variant,
        "pbo": pbo,
        "pbo_n_blocks": n_blocks if pbo is not None else None,
    }


def format_metrics_report(metrics: Dict[str, Any], title: str = "V1 Backtest Report") -> str:
    pf = metrics["profit_factor"]
    pf_str = f"{pf:.2f}" if pf is not None else "n/a"
    lines = [
        f"=== {title} ===",
        f"Final PnL:          ${metrics['final_pnl']:,.2f}",
        f"Max Drawdown:       ${metrics['max_drawdown']:,.2f}",
        f"Worst intraday PnL: ${metrics.get('worst_intraday_pnl', 0.0):,.2f}",
        f"Total commission:   ${metrics.get('total_commission', 0.0):,.2f}",
        f"Trades:             {metrics['num_trades']}",
        f"Trading days:       {metrics['trading_days']}",
        f"Trades / day:       {metrics['trades_per_day']:.2f}",
        f"Win rate:           {metrics['win_rate']:.1%}",
        f"Expectancy / trade: ${metrics['expectancy_per_trade']:,.2f}",
        f"Avg win / avg loss: ${metrics['avg_win']:,.2f} / ${metrics['avg_loss']:,.2f}",
        f"Profit factor:      {pf_str}",
        f"Sharpe (ann.):      {metrics.get('sharpe', 0.0):.3f}",
        f"Locked-out days:    {metrics['locked_out_days']}",
        f"Exit reasons:       {metrics['exit_reasons']}",
    ]
    if metrics.get("n_trials") is not None and "deflated_sharpe" in metrics:
        dpf = metrics.get("deflated_profit_factor")
        dpf_str = f"{dpf:.2f}" if dpf is not None else "n/a"
        lines.extend(
            [
                f"N trials:           {metrics['n_trials']}",
                f"SR (non-ann.):      {metrics.get('sharpe_non_annualised', 0.0):.4f}",
                f"SR0 (null max):     {metrics.get('sr0_null_max', 0.0):.4f}",
                f"Deflated Sharpe:    {metrics['deflated_sharpe']:.4f}  "
                f"(prob={metrics.get('deflated_sharpe_prob', float('nan')):.3f})",
                f"PSR:                {metrics.get('probabilistic_sharpe', float('nan')):.3f}",
                f"Deflated PF:        {dpf_str}",
            ]
        )
    return "\n".join(lines)


def format_multi_variant_report(summary: Dict[str, Any], title: str = "Multi-variant report") -> str:
    lines = [
        f"=== {title} ===",
        f"N trials:  {summary.get('n_trials')}",
        f"PBO:       {summary.get('pbo')}",
        f"PBO blocks:{summary.get('pbo_n_blocks')}",
        "",
    ]
    for name, m in summary.get("variants", {}).items():
        pf = m.get("profit_factor")
        pf_str = f"{pf:.2f}" if pf is not None else "n/a"
        dsr = m.get("deflated_sharpe")
        dsr_str = f"{dsr:.3f}" if dsr is not None else "n/a"
        lines.append(
            f"  {name}: PnL=${m.get('final_pnl', 0):,.0f}  PF={pf_str}  "
            f"Sharpe={m.get('sharpe', 0):.2f}  DSR={dsr_str}"
        )
    return "\n".join(lines)


# Re-export for convenience
__all__ = [
    "summarize_backtest",
    "summarize_multi_variant",
    "format_metrics_report",
    "format_multi_variant_report",
    "deflated_sharpe",
    "probability_backtest_overfitting",
    "equity_to_returns",
]
