"""
Backtest metrics for V1 research reports.
"""

from __future__ import annotations

from typing import Any, Dict, List

import numpy as np
import pandas as pd

from backtest.engine import BacktestResult, Trade


def summarize_backtest(result: BacktestResult) -> Dict[str, Any]:
    trades: List[Trade] = result.trades
    pnls = np.array([t.pnl for t in trades], dtype=float) if trades else np.array([])

    n = len(pnls)
    wins = pnls[pnls > 0] if n else np.array([])
    losses = pnls[pnls <= 0] if n else np.array([])

    # Trading days from equity curve or trade exits
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

    reasons: Dict[str, int] = {}
    for t in trades:
        reasons[t.reason] = reasons.get(t.reason, 0) + 1

    worst = getattr(result, "worst_intraday_pnl", None)
    if worst is None:
        worst = getattr(result, "worst_intraday", 0.0)

    return {
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
        "profit_factor": float(profit_factor) if np.isfinite(profit_factor) else None,
        "gross_profit": gross_profit,
        "gross_loss": gross_loss,
        "exit_reasons": reasons,
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
        f"Locked-out days:    {metrics['locked_out_days']}",
        f"Exit reasons:       {metrics['exit_reasons']}",
    ]
    return "\n".join(lines)
