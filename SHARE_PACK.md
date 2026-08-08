# t3_quant — Agent Handoff

**Purpose:** Share this project with another coding agent without replaying the full chat.  
**Repo path (local):** `C:\Users\jacob\Projects\t3_quant`  
**Status as of:** 2026-08-08  
**Git:** Initialized, **no commits yet**. No remote.

---

## 1. What this project is

Research / prop-trading stack for a **T3 $10k** account with hard **$750 daily loss**, soft **$500** lock. Primary product so far: **MES** continuous futures via Databento.

**Design principle:** Risk manager is the choke point. Strategies propose direction; risk sizes and can lock/flatten. Backtester must mark **adverse bar extremes** before decisions.

This is a **research platform**, not a live trading system. No broker bridge yet.

---

## 2. Account constraints (`config/settings.py`)

| Rule | Value |
|------|------:|
| Account size | $10,000 |
| Hard daily loss | $750 |
| Soft daily loss | $500 |
| Max planned risk/day | $350 |
| Commission | $0.50 / contract / side |
| Platform fee (tracked, unused in PnL) | $574 / mo |
| Products | MES (max 10), ES (1), MGC (5), SIL (5) |

---

## 3. Architecture

```text
Databento (GLBX.MDP3 continuous)
    → data/databento_loader.py → data/parquet/*.parquet (+ session_start)
    → features/ (indicators, multi_tf, session_levels)
    → strategies/ (ensemble, tightened, supertrend regime)
    → risk/daily_risk_manager.py (V2 hard-limit capped flatten)
    → backtest/engine.py (V2 adverse-price first)
    → analytics/metrics.py + analytics/output/ (gitignored CSVs)
```

### Key modules

| Path | Role |
|------|------|
| `config/settings.py` | T3 limits + contract specs |
| `risk/daily_risk_manager.py` | Soft/hard lock, sizing, capped hard flatten, commissions |
| `backtest/engine.py` | Adverse OHLC marking, stop-on-extreme, session EOD flat |
| `data/databento_loader.py` | Fetch continuous + Parquet cache |
| `data/bars.py` | Resample + RTH filter |
| `features/indicators.py` | SuperTrend (NumPy loop), MA, VWAP, LinReg, CPR helpers |
| `features/multi_tf.py` | Higher-TF alignment gate |
| `strategies/weighted_ensemble.py` | 4-way equal-weight (legacy) |
| `strategies/supertrend_regime.py` | 15m ST regime + optional VWAP pullback + MTF |
| `strategies/tight_ensemble.py` | Entry window / pullback / cooldown on ensemble |
| `backtest/run_v1.py` | Gated ensemble runner |
| `backtest/run_v1_ablation.py` | MTF/CPR ablation |
| `backtest/run_v1_tighten.py` | Tightening ablation |
| `backtest/run_regime_spec.py` | Regime-only / pullback / full |
| `backtest/run_regime_15m.py` | Same on 15m primary bars |
| `scripts/pull_mes_long_history.py` | Multi-year MES via 1m chunks → 5m Parquet |
| `tests/test_risk_hard_limit.py` | Hard-limit unit tests |
| `tests/test_backtester_adverse.py` | Adverse air-pocket BT test |

### Secrets / gitignore

- **`.env`** holds `DATABENTO_API_KEY` — **never commit**. Already gitignored.
- `data/parquet/`, `*.parquet`, `analytics/output/` gitignored.
- Do **not** make the repo public while `.env` exists locally unless you confirm it is not staged.

---

## 4. Research conclusions so far (important)

All tests used ~**Feb–Aug 2025** MES continuous from cached 1m Parquet (`MES_v0_ohlcv-1m_2025-02-01_2025-08-01.parquet`), RTH filtered, risk V2 + adverse backtester.

### Ablation (5m equal-weight ensemble)

| Variant | Final PnL | PF | Trades/day | Notes |
|---------|----------:|---:|-----------:|-------|
| MTF only | best of set | ~1.04 | ~2.5 | Keep MTF |
| Full MTF+CPR | worse | 0.93 | ~2.5 | CPR hurt |
| CPR only | worst | 0.76 | ~4 | Drop CPR as coded |
| Neither | noisy | 0.93 | ~5.3 | — |

### Tightening pass (MTF-only + filters)

Further filtering (10:00–11:30, VWAP pullback, cooldown) **did not unlock edge**. Full tighten → PF **0.54**.

### SuperTrend regime redesign (5m primary)

Hypothesis PF 1.3–1.7 **failed**.

| Variant | Final PnL | PF | Trades/day | Worst intraday |
|---------|----------:|---:|-----------:|---------------:|
| ensemble_mtf ref | -$248 | 1.33* | 3.65 | -$459 |
| regime_only | -$140 | 0.93 | 2.91 | -$321 |
| regime_pullback | -$78 | 0.69 | 2.35 | -$315 |
| regime_full | -$78 | 0.61 | 1.43 | -$315 |

\*Trade blotter PF can disagree with equity (risk ledger charges commissions). Prefer equity / worst intraday for survival.

**VWAP-at-value pullback hurt** when tied to these directional cores.

### Option A: 15m primary (same regime family)

| Variant | Final PnL | PF | Trades/day | Worst intraday |
|---------|----------:|---:|-----------:|---------------:|
| ensemble_mtf ref | $0 | 1.51* | 1.34 | -$527 (1 lock) |
| regime_only | -$56 | 0.95 | 1.70 | -$512 |
| regime_pullback | -$102 | 0.53 | 1.22 | -$461 |
| regime_full | $0 | 0.52 | 0.44 | -$219 |

**Conclusion:** MES **trend-following** (ensemble or SuperTrend regime) on 5m/15m has **not cleared costs** on this sample. Filters reduce noise; they do not create edge.

### Risk system (done / trustworthy)

- Hard limit capped flatten (cannot print past −$750 in tests).
- Soft lock blocks new risk; BT can flatten at stop on lock.
- Worst intraday tracked; session EOD flatten (RTH-flat policy).
- Verified: unit tests + full-sample worst often in soft territory (e.g. −$458).

---

## 5. Data notes

- Databento schemas available: `ohlcv-1s`, `ohlcv-1m`, `ohlcv-1h`, `ohlcv-1d` — **no native `ohlcv-5m`**.
- Long history script pulls **1m by year**, resamples to **5m**, writes  
  `data/parquet/MES_v0_ohlcv-5m_2019-05-06_latest.parquet`.
- Longer history is intended as a **validation set**, not a blocker for research.

---

## 6. Recommended next work (paused here)

Priority order agreed before pause:

1. **Do not keep redesigning SuperTrend** for MES 5m/15m trend.
2. Next strategy candidates:
   - **Mean-reversion** (fade VWAP / ORB extension) on 5m or 15m, **or**
   - Tight **15m ensemble ablation** only if one last MES trend look is wanted (blotter PF looked better; equity not a clean uptrend).
   - Later: **gold/silver ratio** sleeve on same risk stack.
3. Use multi-year MES 5m cache to **validate** anything with PF ≫ 1 on the short sample.

---

## 7. How to run (local)

```bash
cd C:\Users\jacob\Projects\t3_quant
python -m pip install -r requirements.txt
# Ensure .env has DATABENTO_API_KEY

python example_usage.py                  # synthetic smoke
python -m backtest.run_v1                # ensemble gates
python -m backtest.run_v1_ablation
python -m backtest.run_regime_spec       # 5m regime variants
python -m backtest.run_regime_15m        # 15m regime variants
python tests/test_risk_hard_limit.py
python tests/test_backtester_adverse.py
```

---

## 8. Sharing with another agent

### Option A — Private GitHub repo (recommended)

1. First commit **without** `.env` / parquet / `analytics/output`.
2. Create a **private** GitHub repo and push.
3. Give the other agent: clone URL + “read `HANDOFF.md` first”.

Public is only OK if you accept sharing strategy code and you **verify** `.env` never lands in history.

### Option B — Single pack file

Generate a pasteable dump (code + this handoff, no secrets):

```bash
python scripts/export_share_pack.py
```

Creates `SHARE_PACK.md` (gitignored). Upload or paste into the other chat.

### Option C — Zip

Zip the repo excluding `.env`, `.venv`, `data/parquet`, `analytics/output`, `__pycache__`.

---

## 9. Open implementation details for the next agent

- `SimpleBacktester` uses **continuous target** signals (`+1/−1/0`), not entry pulses. Strategies that only pulse entries must hold state while regime is valid (`SuperTrendRegimeStrategy` already does).
- `multi_tf_alignment(..., required_agreement=0.75)` — kwarg name is `required_agreement`, not `agreement`.
- Risk manager: `self.risk` on strategies, not `self.risk_manager`.
- Windows console: avoid Unicode arrows in prints (cp1252).
- Adaptive ensemble weights exist but are **off** for baselines (`use_adaptive_weights=False`).

---

## 10. Explicit non-goals (for now)

- Live Rithmic / TradingView webhook execution
- Making the failed SuperTrend+VWAP sleeve “work” via more filters
- Committing Databento keys or Parquet caches


---

# Source dump

## `.gitignore`

```text
.env
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
data/parquet/
*.parquet
.ipynb_checkpoints/
analytics/output/
SHARE_PACK.md
*.zip

```

## `analytics/__init__.py`

```python
from .metrics import summarize_backtest

```

## `analytics/metrics.py`

```python
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

```

## `analytics/output/regime_15m_ensemble_mtf_ref_metrics.txt`

```text
=== 15m regime — ensemble_mtf_ref ===
Final PnL:          $0.00
Max Drawdown:       $-733.25
Worst intraday PnL: $-527.38
Total commission:   $171.00
Trades:             171
Trading days:       128
Trades / day:       1.34
Win rate:           36.8%
Expectancy / trade: $14.87
Avg win / avg loss: $119.26 / $-46.02
Profit factor:      1.51
Locked-out days:    1
Exit reasons:       {'session_eod': 44, 'stop': 92, 'signal': 34, 'risk_lock': 1}

```

## `analytics/output/regime_15m_regime_full_metrics.txt`

```text
=== 15m regime — regime_full ===
Final PnL:          $0.00
Max Drawdown:       $-333.25
Worst intraday PnL: $-218.62
Total commission:   $56.00
Trades:             56
Trading days:       128
Trades / day:       0.44
Win rate:           32.1%
Expectancy / trade: $-15.61
Avg win / avg loss: $51.60 / $-47.46
Profit factor:      0.52
Locked-out days:    0
Exit reasons:       {'signal': 22, 'stop': 34}

```

## `analytics/output/regime_15m_regime_only_metrics.txt`

```text
=== 15m regime — regime_only ===
Final PnL:          $-55.81
Max Drawdown:       $-473.56
Worst intraday PnL: $-512.44
Total commission:   $218.00
Trades:             218
Trading days:       128
Trades / day:       1.70
Win rate:           38.5%
Expectancy / trade: $-1.32
Avg win / avg loss: $71.47 / $-46.94
Profit factor:      0.95
Locked-out days:    1
Exit reasons:       {'stop': 118, 'signal': 99, 'risk_lock': 1}

```

## `analytics/output/regime_15m_regime_pullback_metrics.txt`

```text
=== 15m regime — regime_pullback ===
Final PnL:          $-102.00
Max Drawdown:       $-333.25
Worst intraday PnL: $-461.44
Total commission:   $156.00
Trades:             156
Trading days:       128
Trades / day:       1.22
Win rate:           28.2%
Expectancy / trade: $-15.79
Avg win / avg loss: $62.86 / $-46.68
Profit factor:      0.53
Locked-out days:    0
Exit reasons:       {'stop': 99, 'signal': 57}

```

## `analytics/output/regime_15m_summary.csv`

```text
variant,final_pnl,profit_factor,expectancy,win_rate,trades_per_day,trades,worst_intraday,max_dd,locked_days,commission
ensemble_mtf_ref,0.0,1.5116311236294135,14.87171052631579,0.3684210526315789,1.3359375,171,-527.375,-733.25,1,171.0
regime_only,-55.8125,0.9543638965064981,-1.3168004587155964,0.3853211009174312,1.703125,218,-512.4375,-473.5625,1,218.0
regime_pullback,-102.0,0.5290172968191544,-15.785657051282051,0.28205128205128205,1.21875,156,-461.4375,-333.25,0,156.0
regime_full,0.0,0.5150937510830763,-15.614955357142858,0.32142857142857145,0.4375,56,-218.625,-333.25,0,56.0

```

## `analytics/output/regime_spec_ensemble_mtf_ref_metrics.txt`

```text
=== Regime spec — ensemble_mtf_ref ===
Final PnL:          $-248.19
Max Drawdown:       $-991.12
Worst intraday PnL: $-458.81
Total commission:   $467.00
Trades:             467
Trading days:       128
Trades / day:       3.65
Win rate:           28.7%
Expectancy / trade: $6.69
Avg win / avg loss: $93.69 / $-28.31
Profit factor:      1.33
Locked-out days:    0
Exit reasons:       {'stop': 294, 'signal': 131, 'session_eod': 42}

```

## `analytics/output/regime_spec_regime_full_metrics.txt`

```text
=== Regime spec — regime_full ===
Final PnL:          $-78.44
Max Drawdown:       $-528.50
Worst intraday PnL: $-314.94
Total commission:   $183.00
Trades:             183
Trading days:       128
Trades / day:       1.43
Win rate:           22.4%
Expectancy / trade: $-9.25
Avg win / avg loss: $64.02 / $-30.40
Profit factor:      0.61
Locked-out days:    0
Exit reasons:       {'stop': 138, 'signal': 45}

```

## `analytics/output/regime_spec_regime_only_metrics.txt`

```text
=== Regime spec — regime_only ===
Final PnL:          $-140.44
Max Drawdown:       $-668.81
Worst intraday PnL: $-320.56
Total commission:   $373.00
Trades:             373
Trading days:       128
Trades / day:       2.91
Win rate:           26.8%
Expectancy / trade: $-1.63
Avg win / avg loss: $76.16 / $-30.12
Profit factor:      0.93
Locked-out days:    0
Exit reasons:       {'stop': 263, 'signal': 110}

```

## `analytics/output/regime_spec_regime_pullback_metrics.txt`

```text
=== Regime spec — regime_pullback ===
Final PnL:          $-78.44
Max Drawdown:       $-596.81
Worst intraday PnL: $-314.94
Total commission:   $301.00
Trades:             301
Trading days:       128
Trades / day:       2.35
Win rate:           23.3%
Expectancy / trade: $-7.13
Avg win / avg loss: $68.78 / $-30.13
Profit factor:      0.69
Locked-out days:    0
Exit reasons:       {'stop': 222, 'signal': 79}

```

## `analytics/output/regime_spec_summary.csv`

```text
variant,final_pnl,profit_factor,expectancy,win_rate,trades_per_day,trades,worst_intraday,max_dd,locked_days,commission,equity_min,equity_max,pct_bars_above_zero,exit_reasons
ensemble_mtf_ref,-248.1875,1.331611953754773,6.694726980728052,0.28693790149892934,3.6484375,467,-458.8125,-991.125,0,467.0,-341.5,649.625,0.36004894463138576,"{'stop': 294, 'signal': 131, 'session_eod': 42}"
regime_only,-140.4375,0.9261046679536092,-1.6291890080428955,0.2680965147453083,2.9140625,373,-320.5625,-668.8125,0,373.0,-279.0,389.8125,0.40889160803507696,"{'stop': 263, 'signal': 110}"
regime_pullback,-78.4375,0.6916971204353018,-7.129568106312292,0.23255813953488372,2.3515625,301,-314.9375,-596.8125,0,301.0,-248.0,348.8125,0.251249107780157,"{'stop': 222, 'signal': 79}"
regime_full,-78.4375,0.6080466759323604,-9.246243169398907,0.22404371584699453,1.4296875,183,-314.9375,-528.5,0,183.0,-248.0,280.5,0.16783929846028348,"{'stop': 138, 'signal': 45}"

```

## `analytics/output/v1_ablation_cpr_only_metrics.txt`

```text
=== V1 MES 5m Ensemble (MTF=OFF CPR=ON, equal weight) ===
Final PnL:          $-451.25
Max Drawdown:       $-2,117.50
Trades:             505
Trading days:       128
Trades / day:       3.95
Win rate:           24.0%
Expectancy / trade: $-9.23
Avg win / avg loss: $123.06 / $-50.91
Profit factor:      0.76
Locked-out days:    3
Exit reasons:       {'stop': 248, 'signal': 250, 'reverse': 6, 'eod': 1}

```

## `analytics/output/v1_ablation_full_metrics.txt`

```text
=== V1 MES 5m Ensemble (MTF=ON CPR=ON, equal weight) ===
Final PnL:          $-117.50
Max Drawdown:       $-2,711.25
Trades:             317
Trading days:       128
Trades / day:       2.48
Win rate:           29.0%
Expectancy / trade: $-2.77
Avg win / avg loss: $120.49 / $-53.17
Profit factor:      0.93
Locked-out days:    1
Exit reasons:       {'stop': 155, 'signal': 161, 'eod': 1}

```

## `analytics/output/v1_ablation_mtf_only_metrics.txt`

```text
=== V1 MES 5m Ensemble (MTF=ON CPR=OFF, equal weight) ===
Final PnL:          $-86.25
Max Drawdown:       $-2,663.75
Trades:             319
Trading days:       128
Trades / day:       2.49
Win rate:           32.0%
Expectancy / trade: $1.53
Avg win / avg loss: $125.37 / $-56.69
Profit factor:      1.04
Locked-out days:    1
Exit reasons:       {'signal': 155, 'stop': 163, 'eod': 1}

```

## `analytics/output/v1_ablation_neither_metrics.txt`

```text
=== V1 MES 5m Ensemble (MTF=OFF CPR=OFF, equal weight) ===
Final PnL:          $-336.25
Max Drawdown:       $-2,095.00
Trades:             682
Trading days:       128
Trades / day:       5.33
Win rate:           27.1%
Expectancy / trade: $-2.56
Avg win / avg loss: $123.95 / $-49.65
Profit factor:      0.93
Locked-out days:    3
Exit reasons:       {'signal': 233, 'reverse': 90, 'stop': 356, 'risk_lock': 2, 'eod': 1}

```

## `analytics/output/v1_ablation_summary.csv`

```text
variant,mtf,cpr,final_pnl,max_dd,trades,trades_per_day,win_rate,expectancy,avg_win,avg_loss,profit_factor,locked_days
full,True,True,-117.5,-2711.25,317,2.4765625,0.2902208201892745,-2.7705047318611986,120.4945652173913,-53.172222222222224,0.9265907428690837,1
mtf_only,True,False,-86.25,-2663.75,319,2.4921875,0.31974921630094044,1.5274294670846396,125.37254901960785,-56.685483870967744,1.039611405808589,1
cpr_only,False,True,-451.25,-2117.5,505,3.9453125,0.2396039603960396,-9.227722772277227,123.0599173553719,-50.912109375,0.7616398767279191,3
neither,False,False,-336.25,-2095.0,682,5.328125,0.27126099706744866,-2.5597507331378297,123.95270270270271,-49.65191146881288,0.9292559873566479,3

```

## `analytics/output/v1_mes_5m_metrics.txt`

```text
=== V1 MES 5m Gated Ensemble (MTF + CPR, equal weight) ===
Final PnL:          $-117.50
Max Drawdown:       $-2,711.25
Trades:             317
Trading days:       128
Trades / day:       2.48
Win rate:           29.0%
Expectancy / trade: $-2.77
Avg win / avg loss: $120.49 / $-53.17
Profit factor:      0.93
Locked-out days:    1
Exit reasons:       {'stop': 155, 'signal': 161, 'eod': 1}

```

## `analytics/output/v1_mtf_only_riskv2_metrics.txt`

```text
=== V1 MES 5m Ensemble (MTF=ON CPR=OFF, equal weight) ===
Final PnL:          $-240.00
Max Drawdown:       $-1,220.25
Worst intraday PnL: $-564.75
Trades:             513
Trading days:       128
Trades / day:       4.01
Win rate:           21.8%
Expectancy / trade: $-2.62
Avg win / avg loss: $93.69 / $-29.52
Profit factor:      0.89
Locked-out days:    1
Exit reasons:       {'stop': 348, 'signal': 121, 'session_eod': 44}

```

## `analytics/output/v1_regime_ensemble_mtf_metrics.txt`

```text
=== V1.2 regime — ensemble_mtf ===
Final PnL:          $-248.19
Max Drawdown:       $-991.12
Worst intraday PnL: $-458.81
Total commission:   $467.00
Trades:             467
Trading days:       128
Trades / day:       3.65
Win rate:           28.7%
Expectancy / trade: $6.69
Avg win / avg loss: $93.69 / $-28.31
Profit factor:      1.33
Locked-out days:    0
Exit reasons:       {'stop': 294, 'signal': 131, 'session_eod': 42}

```

## `analytics/output/v1_regime_st15_regime_vwap_metrics.txt`

```text
=== V1.2 regime — st15_regime_vwap ===
Final PnL:          $-109.44
Max Drawdown:       $-668.81
Worst intraday PnL: $-312.81
Total commission:   $216.00
Trades:             216
Trading days:       128
Trades / day:       1.69
Win rate:           29.6%
Expectancy / trade: $0.85
Avg win / avg loss: $74.60 / $-30.21
Profit factor:      1.04
Locked-out days:    0
Exit reasons:       {'signal': 69, 'stop': 147}

```

## `analytics/output/v1_regime_st5_regime_metrics.txt`

```text
=== V1.2 regime — st5_regime ===
Final PnL:          $-155.00
Max Drawdown:       $-544.81
Worst intraday PnL: $-282.31
Total commission:   $208.00
Trades:             208
Trading days:       128
Trades / day:       1.62
Win rate:           27.9%
Expectancy / trade: $-0.83
Avg win / avg loss: $75.82 / $-30.47
Profit factor:      0.96
Locked-out days:    0
Exit reasons:       {'stop': 146, 'signal': 62}

```

## `analytics/output/v1_regime_st5_regime_vwap_metrics.txt`

```text
=== V1.2 regime — st5_regime_vwap ===
Final PnL:          $-124.00
Max Drawdown:       $-544.81
Worst intraday PnL: $-282.31
Total commission:   $122.00
Trades:             122
Trading days:       128
Trades / day:       0.95
Win rate:           27.0%
Expectancy / trade: $-1.99
Avg win / avg loss: $74.51 / $-30.36
Profit factor:      0.91
Locked-out days:    0
Exit reasons:       {'stop': 87, 'signal': 35}

```

## `analytics/output/v1_regime_summary.csv`

```text
variant,final_pnl,profit_factor,expectancy,win_rate,trades_per_day,trades,worst_intraday,max_dd,locked_days,commission
ensemble_mtf,-248.1875,1.331611953754773,6.694726980728052,0.28693790149892934,3.6484375,467,-458.8125,-991.125,0,467.0
st5_regime,-155.0,0.962281181619256,-0.8287259615384616,0.27884615384615385,1.625,208,-282.3125,-544.8125,0,208.0
st5_regime_vwap,-124.0,0.909978257852616,-1.9938524590163935,0.27049180327868855,0.953125,122,-282.3125,-544.8125,0,122.0
st15_regime_vwap,-109.4375,1.0398001823948166,0.8460648148148148,0.2962962962962963,1.6875,216,-312.8125,-668.8125,0,216.0

```

## `analytics/output/v1_tighten_baseline_mtf_metrics.txt`

```text
=== V1.1 tighten — baseline_mtf ===
Final PnL:          $-248.19
Max Drawdown:       $-991.12
Worst intraday PnL: $-458.81
Total commission:   $467.00
Trades:             467
Trading days:       128
Trades / day:       3.65
Win rate:           28.7%
Expectancy / trade: $6.69
Avg win / avg loss: $93.69 / $-28.31
Profit factor:      1.33
Locked-out days:    0
Exit reasons:       {'stop': 294, 'signal': 131, 'session_eod': 42}

```

## `analytics/output/v1_tighten_pullback_only_metrics.txt`

```text
=== V1.1 tighten — pullback_only ===
Final PnL:          $-124.00
Max Drawdown:       $-1,191.31
Worst intraday PnL: $-750.00
Total commission:   $216.00
Trades:             216
Trading days:       128
Trades / day:       1.69
Win rate:           18.1%
Expectancy / trade: $-8.19
Avg win / avg loss: $83.96 / $-28.50
Profit factor:      0.65
Locked-out days:    1
Exit reasons:       {'stop': 156, 'signal': 55, 'session_eod': 4, 'hard_limit': 1}

```

## `analytics/output/v1_tighten_summary.csv`

```text
variant,final_pnl,profit_factor,expectancy,win_rate,trades_per_day,trades,worst_intraday,max_dd,locked_days,commission
baseline_mtf,-248.1875,1.331611953754773,6.694726980728052,0.28693790149892934,3.6484375,467,-458.8125,-991.125,0,467.0
tight_full,-93.0,0.5426292564362744,-10.353632478632479,0.21367521367521367,0.9140625,117,-253.9375,-342.6875,0,117.0
window_only,-155.0,1.0402881998521245,0.8250644329896907,0.29381443298969073,1.515625,194,-193.0625,-544.8125,0,194.0
pullback_only,-124.0,0.6491506312959223,-8.193287037037036,0.18055555555555555,1.6875,216,-749.9999999999982,-1191.3124999999982,1,216.0

```

## `analytics/output/v1_tighten_tight_full_metrics.txt`

```text
=== V1.1 tighten — tight_full ===
Final PnL:          $-93.00
Max Drawdown:       $-342.69
Worst intraday PnL: $-253.94
Total commission:   $117.00
Trades:             117
Trading days:       128
Trades / day:       0.91
Win rate:           21.4%
Expectancy / trade: $-10.35
Avg win / avg loss: $57.49 / $-28.79
Profit factor:      0.54
Locked-out days:    0
Exit reasons:       {'stop': 83, 'signal': 34}

```

## `analytics/output/v1_tighten_window_only_metrics.txt`

```text
=== V1.1 tighten — window_only ===
Final PnL:          $-155.00
Max Drawdown:       $-544.81
Worst intraday PnL: $-193.06
Total commission:   $194.00
Trades:             194
Trading days:       128
Trades / day:       1.52
Win rate:           29.4%
Expectancy / trade: $0.83
Avg win / avg loss: $72.51 / $-29.00
Profit factor:      1.04
Locked-out days:    0
Exit reasons:       {'stop': 125, 'signal': 69}

```

## `analytics/output/v2_bt_mtf_only_metrics.txt`

```text
=== V1 MES 5m Ensemble (MTF=ON CPR=OFF, equal weight) ===
Final PnL:          $-248.19
Max Drawdown:       $-991.12
Worst intraday PnL: $-458.81
Total commission:   $467.00
Trades:             467
Trading days:       128
Trades / day:       3.65
Win rate:           28.7%
Expectancy / trade: $6.69
Avg win / avg loss: $93.69 / $-28.31
Profit factor:      1.33
Locked-out days:    0
Exit reasons:       {'stop': 294, 'signal': 131, 'session_eod': 42}

```

## `analytics/output/v2_bt_tight_mtf_only_metrics.txt`

```text
=== V1 MES 5m Ensemble (MTF=ON CPR=OFF, equal weight) ===
Final PnL:          $-248.19
Max Drawdown:       $-991.12
Worst intraday PnL: $-458.81
Total commission:   $467.00
Trades:             467
Trading days:       128
Trades / day:       3.65
Win rate:           28.7%
Expectancy / trade: $6.69
Avg win / avg loss: $93.69 / $-28.31
Profit factor:      1.33
Locked-out days:    0
Exit reasons:       {'stop': 294, 'signal': 131, 'session_eod': 42}

```

## `backtest/__init__.py`

```python
from .engine import SimpleBacktester, BacktestResult, Trade

```

## `backtest/engine.py`

```python
"""
Event-driven backtest engine V2
Hard guarantee: risk manager sees adverse prices before any decision.
A stop or risk lock is always executed at the stop price, not the close.
"""

from __future__ import annotations

import pandas as pd
import numpy as np
from typing import Dict, Optional
from dataclasses import dataclass, field

from risk.daily_risk_manager import DailyRiskManager
from strategies.base import StrategyBase
from config.settings import CONTRACTS, ACCOUNT


@dataclass
class Trade:
    symbol: str
    entry_time: pd.Timestamp
    exit_time: Optional[pd.Timestamp]
    qty: int
    entry_price: float
    exit_price: Optional[float]
    pnl: float = 0.0
    reason: str = ""


@dataclass
class BacktestResult:
    trades: list = field(default_factory=list)
    equity_curve: pd.Series = field(default_factory=pd.Series)
    final_pnl: float = 0.0
    max_dd: float = 0.0
    num_trades: int = 0
    locked_out_days: int = 0
    worst_intraday: float = 0.0  # most negative equity seen
    worst_intraday_pnl: float = 0.0  # alias for analytics compatibility
    total_commission: float = 0.0


class SimpleBacktester:
    """
    Bar-by-bar backtester that respects the DailyRiskManager.

    Key design rules:
      - The risk manager always sees the *adverse* price of a bar first.
      - Stops are triggered on the extreme, not the close.
      - Risk-lock flattening uses the stop price, not the close.
      - No new entry is allowed unless the risk manager passes *after*
        seeing the adverse price for the current bar.
      - RTH-flat: open positions are closed before day rollover.
    """

    def __init__(
        self,
        strategy: StrategyBase,
        risk_manager: DailyRiskManager,
        symbol: str = "MES",
        stop_points: float = 8.0,
        commission_per_side: float = ACCOUNT.commission_per_contract,
        slippage_ticks: float = 1.0,
    ):
        self.strategy = strategy
        self.risk = risk_manager
        self.symbol = symbol
        self.stop_points = stop_points
        self.commission = commission_per_side
        self.slippage_ticks = slippage_ticks
        self.spec = CONTRACTS[symbol]

    # ------------------------------------------------------------------
    # Public entry point
    # ------------------------------------------------------------------
    def run(
        self,
        data: pd.DataFrame,
        higher_tf: Optional[Dict[str, pd.Series]] = None,
        cpr: Optional[dict] = None,
        orb: Optional[tuple] = None,
    ) -> BacktestResult:
        """
        data must contain: open, high, low, close, session_start
        """
        signals = self.strategy.generate_signals(
            data,
            higher_tf_closes=higher_tf,
            cpr_levels=cpr,
            orb_high=orb[0] if orb else None,
            orb_low=orb[1] if orb else None,
        )

        equity = []
        trades = []
        locked_days = set()
        worst_intraday = 0.0

        position = 0
        entry_price = 0.0
        entry_time = None
        prev_ts = None
        prev_close = None

        for i, (ts, row) in enumerate(data.iterrows()):
            # --- 0. RTH-flat before day rollover ---
            if (
                prev_ts is not None
                and ts.date() != prev_ts.date()
                and position != 0
                and prev_close is not None
            ):
                self._close(
                    position,
                    entry_price,
                    prev_close,
                    entry_time,
                    prev_ts,
                    trades,
                    "session_eod",
                )
                position = 0
                entry_time = None
                worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)

            # --- 1. Day reset ---
            self.risk.reset_day(ts.date())

            # --- 2. Flat: permission check only (no fake adverse mark) ---
            if position == 0:
                if not self.risk.can_take_new_risk():
                    locked_days.add(ts.date())
                    equity.append(self.risk.total_pnl)
                    worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)
                    prev_ts, prev_close = ts, float(row["close"])
                    continue

                # --- 3. New entry (only if still unlocked) ---
                target = signals.iloc[i]
                if target != 0 and self.risk.can_take_new_risk():
                    size = self.strategy.size_position(
                        self.symbol, int(target), self.stop_points
                    )
                    if size != 0:
                        position = size
                        entry_price = self._slipped(ts, row, size, is_entry=True)
                        entry_time = ts
                        self.risk.record_fill(self.symbol, size, entry_price)

                equity.append(self.risk.total_pnl)
                worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, float(row["close"])
                continue

            # ==========================================================
            # POSITION IS OPEN
            # Order: adverse mark → hard sync → risk lock → stop → signals
            # ==========================================================

            # --- 4. Adverse extreme + stop level ---
            if position > 0:
                adverse_price = float(row["low"])
                stop_price = entry_price - self.stop_points
                stop_hit = adverse_price <= stop_price
            else:
                adverse_price = float(row["high"])
                stop_price = entry_price + self.stop_points
                stop_hit = adverse_price >= stop_price

            # --- 5. Risk manager sees worst case first ---
            was_open = self.symbol in self.risk.open_positions
            self.risk.update_unrealized(self.symbol, adverse_price)

            # Hard limit may have force-flattened inside the risk manager
            if was_open and self.symbol not in self.risk.open_positions:
                locked_days.add(ts.date())
                # Prefer stop if touched; else adverse (risk already capped internally)
                exit_px = stop_price if stop_hit else adverse_price
                self._record_external_flatten(
                    position, entry_price, exit_px, entry_time, ts, trades, "hard_limit"
                )
                position = 0
                entry_time = None
                equity.append(self.risk.total_pnl)
                worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, float(row["close"])
                continue

            # --- 6. Soft/hard lock → flatten at stop, then continue (no same-bar re-entry) ---
            if not self.risk.can_take_new_risk():
                locked_days.add(ts.date())
                self._close(
                    position, entry_price, stop_price, entry_time, ts, trades, "risk_lock"
                )
                position = 0
                entry_time = None
                equity.append(self.risk.total_pnl)
                worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, float(row["close"])
                continue

            # --- 7. Explicit stop: bar range must actually touch stop_price ---
            if stop_hit:
                self._close(
                    position, entry_price, stop_price, entry_time, ts, trades, "stop"
                )
                position = 0
                entry_time = None
                equity.append(self.risk.total_pnl)
                worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, float(row["close"])
                continue

            # --- 8. Signals only after adverse + lock + stop checks pass ---
            if not self.risk.can_take_new_risk():
                locked_days.add(ts.date())
                equity.append(self.risk.total_pnl)
                worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, float(row["close"])
                continue

            target = signals.iloc[i]

            if target == 0:
                exit_px = self._slipped(ts, row, position, is_entry=False)
                self._close(
                    position, entry_price, exit_px, entry_time, ts, trades, "signal"
                )
                position = 0
                entry_time = None

            elif np.sign(target) != np.sign(position):
                exit_px = self._slipped(ts, row, position, is_entry=False)
                self._close(
                    position, entry_price, exit_px, entry_time, ts, trades, "reverse"
                )
                position = 0
                entry_time = None
                # Re-check before opening the opposite side on this same bar
                if self.risk.can_take_new_risk():
                    size = self.strategy.size_position(
                        self.symbol, int(target), self.stop_points
                    )
                    if size != 0:
                        position = size
                        entry_price = self._slipped(ts, row, size, is_entry=True)
                        entry_time = ts
                        self.risk.record_fill(self.symbol, size, entry_price)

            equity.append(self.risk.total_pnl)
            worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)
            prev_ts, prev_close = ts, float(row["close"])

        # --- 9. End-of-sample flatten ---
        if position != 0:
            final_close = float(data["close"].iloc[-1])
            self._close(
                position,
                entry_price,
                final_close,
                entry_time,
                data.index[-1],
                trades,
                "eod",
            )
            worst_intraday = min(worst_intraday, self.risk.worst_pnl_today)

        # --- 10. Build result ---
        eq = pd.Series(equity, index=data.index[: len(equity)])
        max_dd = (eq - eq.cummax()).min() if len(eq) else 0.0
        total_comm = sum(abs(t.qty) * self.commission * 2 for t in trades)
        worst = float(worst_intraday)

        return BacktestResult(
            trades=trades,
            equity_curve=eq,
            final_pnl=float(eq.iloc[-1]) if len(eq) else 0.0,
            max_dd=float(max_dd),
            num_trades=len(trades),
            locked_out_days=len(locked_days),
            worst_intraday=worst,
            worst_intraday_pnl=worst,
            total_commission=float(total_comm),
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _slipped(
        self,
        ts: pd.Timestamp,
        bar: pd.Series,
        qty: int,
        is_entry: bool,
    ) -> float:
        """
        Return a realistic fill price with slippage.
        Uses bar VWAP approximation (OHLC average) + adverse ticks.
        Stop / risk_lock exits bypass this — callers pass the stop price.
        """
        base = (
            float(bar["open"])
            + float(bar["high"])
            + float(bar["low"])
            + float(bar["close"])
        ) / 4.0
        slip = self.slippage_ticks * self.spec.tick_size
        direction = 1 if qty > 0 else -1
        if is_entry:
            return base + direction * slip
        return base - direction * slip

    def _record_external_flatten(
        self,
        qty: int,
        entry: float,
        exit_raw: float,
        entry_time: pd.Timestamp,
        ts: pd.Timestamp,
        trades: list,
        reason: str,
    ) -> None:
        """Risk manager already realized the flatten — log trade only."""
        points = (float(exit_raw) - entry) * np.sign(qty)
        gross = points * abs(qty) * self.spec.multiplier
        costs = abs(qty) * self.commission * 2
        trades.append(
            Trade(
                symbol=self.symbol,
                entry_time=entry_time,
                exit_time=ts,
                qty=qty,
                entry_price=entry,
                exit_price=float(exit_raw),
                pnl=gross - costs,
                reason=reason,
            )
        )

    def _close(
        self,
        qty: int,
        entry: float,
        exit_price: float,
        entry_time: pd.Timestamp,
        ts: pd.Timestamp,
        trades: list,
        reason: str,
    ) -> float:
        """
        Record a closing trade. For stop / risk-lock exits the caller
        has already passed the stop price, NOT the close.
        """
        exit_price = float(exit_price)
        points = (exit_price - entry) * np.sign(qty)
        gross = points * abs(qty) * self.spec.multiplier
        costs = abs(qty) * self.commission * 2
        pnl = gross - costs

        self.risk.record_fill(self.symbol, -qty, exit_price, is_closing=True)

        trades.append(
            Trade(
                symbol=self.symbol,
                entry_time=entry_time,
                exit_time=ts,
                qty=qty,
                entry_price=entry,
                exit_price=exit_price,
                pnl=pnl,
                reason=reason,
            )
        )
        return pnl

```

## `backtest/run_regime_15m.py`

```python
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

```

## `backtest/run_regime_spec.py`

```python
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

```

## `backtest/run_v1.py`

```python
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

```

## `backtest/run_v1_ablation.py`

```python
"""
V1 gate ablation: same 5m MES setup, four gate combinations.

  1. Full     — MTF ON  + CPR ON   (original V1)
  2. MTF only — MTF ON  + CPR OFF
  3. CPR only — MTF OFF + CPR ON
  4. Neither  — MTF OFF + CPR OFF  (raw equal-weight ensemble)

Usage:
  python -m backtest.run_v1_ablation
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backtest.run_v1 import OUT_DIR, run_v1

# Risk-manager CRITICAL logs are noisy across four runs; keep warnings visible.
logging.getLogger("risk.daily_risk_manager").setLevel(logging.ERROR)

VARIANTS = [
    ("full", True, True),
    ("mtf_only", True, False),
    ("cpr_only", False, True),
    ("neither", False, False),
]


def main() -> None:
    rows = []
    print("V1 ablation — preparing data once, then four gate variants...\n")

    for name, use_mtf, use_cpr in VARIANTS:
        print(f"--- {name} ---")
        out = run_v1(
            use_mtf=use_mtf,
            use_cpr=use_cpr,
            tag=f"v1_ablation_{name}",
            save=True,
            quiet=False,
        )
        m = out["metrics"]
        rows.append(
            {
                "variant": name,
                "mtf": use_mtf,
                "cpr": use_cpr,
                "final_pnl": m["final_pnl"],
                "max_dd": m["max_drawdown"],
                "trades": m["num_trades"],
                "trades_per_day": m["trades_per_day"],
                "win_rate": m["win_rate"],
                "expectancy": m["expectancy_per_trade"],
                "avg_win": m["avg_win"],
                "avg_loss": m["avg_loss"],
                "profit_factor": m["profit_factor"],
                "locked_days": m["locked_out_days"],
            }
        )
        print()

    summary = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "v1_ablation_summary.csv"
    summary.to_csv(csv_path, index=False)

    # Compact comparison table for the terminal
    show = summary.copy()
    show["final_pnl"] = show["final_pnl"].map(lambda x: f"${x:,.2f}")
    show["max_dd"] = show["max_dd"].map(lambda x: f"${x:,.2f}")
    show["expectancy"] = show["expectancy"].map(lambda x: f"${x:,.2f}")
    show["win_rate"] = show["win_rate"].map(lambda x: f"{x:.1%}")
    show["trades_per_day"] = show["trades_per_day"].map(lambda x: f"{x:.2f}")
    show["profit_factor"] = show["profit_factor"].map(
        lambda x: f"{x:.2f}" if x is not None else "n/a"
    )

    print("=== Ablation summary ===")
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
                "max_dd",
                "locked_days",
            ]
        ].to_string(index=False)
    )
    print(f"\nSaved -> {csv_path}")


if __name__ == "__main__":
    main()

```

## `backtest/run_v1_regime.py`

```python
"""
V1.2 — SuperTrend regime redesign vs legacy ensemble.

Variants:
  A) ensemble_mtf          — old equal-weight + MTF (reference)
  B) st5_regime            — 5m SuperTrend regime + MTF, no pullback
  C) st5_regime_vwap       — 5m SuperTrend + MTF + VWAP pullback-resume
  D) st15_regime_vwap      — 15m SuperTrend regime + VWAP pullback-resume (no MTF)

Usage:
  python -m backtest.run_v1_regime
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
    stop_points: float = 6.0,
) -> dict[str, Any]:
    data, higher_tf, _ = prepare_mes_5m()
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
    stem = f"v1_regime_{name}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = format_metrics_report(metrics, title=f"V1.2 regime — {name}")
    (OUT_DIR / f"{stem}_metrics.txt").write_text(report + "\n", encoding="utf-8")
    if result.trades:
        pd.DataFrame(
            [
                {
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
        ).to_csv(OUT_DIR / f"{stem}_trades.csv", index=False)
    print(report)
    print()
    return {"name": name, "metrics": metrics, "result": result}


def main() -> None:
    print("Preparing MES 5m once...\n")
    prepare_mes_5m()

    variants = [
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
            "st5_regime",
            True,
            lambda risk: SuperTrendRegimeStrategy(
                risk_manager=risk,
                regime_tf="5min",
                use_mtf=True,
                require_pullback=False,
                min_regime_bars=3,
                entry_start="10:00",
                entry_end="11:30",
                cooldown_bars=6,
                flatten_outside_window=True,
            ),
        ),
        (
            "st5_regime_vwap",
            True,
            lambda risk: SuperTrendRegimeStrategy(
                risk_manager=risk,
                regime_tf="5min",
                use_mtf=True,
                require_pullback=True,
                min_regime_bars=3,
                entry_start="10:00",
                entry_end="11:30",
                cooldown_bars=6,
                flatten_outside_window=True,
            ),
        ),
        (
            "st15_regime_vwap",
            False,
            lambda risk: SuperTrendRegimeStrategy(
                risk_manager=risk,
                regime_tf="15min",
                use_mtf=False,  # 15m ST is the regime; avoid double higher-TF lag
                require_pullback=True,
                min_regime_bars=2,  # counted on native 15m SuperTrend bars
                entry_start="10:00",
                entry_end="11:30",
                cooldown_bars=6,
                flatten_outside_window=True,
            ),
        ),
    ]

    rows = []
    for name, use_mtf_data, factory in variants:
        print(f"--- {name} ---")
        out = _run(name, factory, use_mtf_data=use_mtf_data)
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
    path = OUT_DIR / "v1_regime_summary.csv"
    summary.to_csv(path, index=False)

    show = summary.copy()
    for col, fmt in [
        ("final_pnl", "${:,.2f}"),
        ("expectancy", "${:,.2f}"),
        ("worst_intraday", "${:,.2f}"),
        ("max_dd", "${:,.2f}"),
        ("commission", "${:,.2f}"),
    ]:
        show[col] = show[col].map(lambda x, f=fmt: f.format(x))
    show["win_rate"] = show["win_rate"].map(lambda x: f"{x:.1%}")
    show["trades_per_day"] = show["trades_per_day"].map(lambda x: f"{x:.2f}")
    show["profit_factor"] = show["profit_factor"].map(
        lambda x: f"{x:.2f}" if x is not None else "n/a"
    )

    print("=== Regime redesign summary ===")
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

```

## `backtest/run_v1_tighten.py`

```python
"""
V1.1 tightening pass on the MTF-only ensemble.

Compares:
  A) Baseline MTF-only (no CPR)
  B) Tightened: 10:00–11:30 window + VWAP pullback + 6-bar cooldown
  C) Ablation: window only (no pullback)
  D) Ablation: pullback only (full RTH window 09:30–16:00)

Usage:
  python -m backtest.run_v1_tighten
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import pandas as pd

from analytics.metrics import format_metrics_report, summarize_backtest
from backtest.engine import SimpleBacktester
from backtest.run_v1 import OUT_DIR, prepare_mes_5m
from risk.daily_risk_manager import DailyRiskManager
from strategies.tight_ensemble import TightenedEnsembleStrategy
from strategies.weighted_ensemble import WeightedEnsembleStrategy

logging.getLogger("risk.daily_risk_manager").setLevel(logging.ERROR)


def _run(
    name: str,
    strategy_factory,
    *,
    use_mtf: bool = True,
    stop_points: float = 6.0,
) -> dict[str, Any]:
    data, higher_tf, _cpr = prepare_mes_5m()
    risk = DailyRiskManager()
    strategy = strategy_factory(risk)
    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=stop_points,
        slippage_ticks=1.0,
    )
    result = bt.run(data, higher_tf=higher_tf if use_mtf else None, cpr=None)
    metrics = summarize_backtest(result)
    stem = f"v1_tighten_{name}"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    report = format_metrics_report(metrics, title=f"V1.1 tighten — {name}")
    (OUT_DIR / f"{stem}_metrics.txt").write_text(report + "\n", encoding="utf-8")
    if result.trades:
        pd.DataFrame(
            [
                {
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
        ).to_csv(OUT_DIR / f"{stem}_trades.csv", index=False)
    print(report)
    print()
    return {"name": name, "metrics": metrics, "result": result}


def main() -> None:
    print("Preparing MES 5m once...\n")
    prepare_mes_5m()

    variants = [
        (
            "baseline_mtf",
            lambda risk: WeightedEnsembleStrategy(
                risk_manager=risk,
                use_adaptive_weights=False,
                require_cpr_filter=False,
                require_orb_filter=False,
                multi_tf_agreement=0.75,
            ),
        ),
        (
            "tight_full",
            lambda risk: TightenedEnsembleStrategy(
                risk_manager=risk,
                use_adaptive_weights=False,
                require_cpr_filter=False,
                require_orb_filter=False,
                multi_tf_agreement=0.75,
                entry_start="10:00",
                entry_end="11:30",
                require_pullback=True,
                cooldown_bars=6,
                flatten_outside_window=True,
            ),
        ),
        (
            "window_only",
            lambda risk: TightenedEnsembleStrategy(
                risk_manager=risk,
                use_adaptive_weights=False,
                require_cpr_filter=False,
                require_orb_filter=False,
                multi_tf_agreement=0.75,
                entry_start="10:00",
                entry_end="11:30",
                require_pullback=False,
                cooldown_bars=6,
                flatten_outside_window=True,
            ),
        ),
        (
            "pullback_only",
            lambda risk: TightenedEnsembleStrategy(
                risk_manager=risk,
                use_adaptive_weights=False,
                require_cpr_filter=False,
                require_orb_filter=False,
                multi_tf_agreement=0.75,
                entry_start="09:30",
                entry_end="16:00",
                require_pullback=True,
                cooldown_bars=6,
                flatten_outside_window=False,
            ),
        ),
    ]

    rows = []
    for name, factory in variants:
        print(f"--- {name} ---")
        out = _run(name, factory)
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
    path = OUT_DIR / "v1_tighten_summary.csv"
    summary.to_csv(path, index=False)

    show = summary.copy()
    show["final_pnl"] = show["final_pnl"].map(lambda x: f"${x:,.2f}")
    show["expectancy"] = show["expectancy"].map(lambda x: f"${x:,.2f}")
    show["worst_intraday"] = show["worst_intraday"].map(lambda x: f"${x:,.2f}")
    show["max_dd"] = show["max_dd"].map(lambda x: f"${x:,.2f}")
    show["win_rate"] = show["win_rate"].map(lambda x: f"{x:.1%}")
    show["trades_per_day"] = show["trades_per_day"].map(lambda x: f"{x:.2f}")
    show["profit_factor"] = show["profit_factor"].map(
        lambda x: f"{x:.2f}" if x is not None else "n/a"
    )
    show["commission"] = show["commission"].map(lambda x: f"${x:,.2f}")

    print("=== Tightening summary ===")
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

```

## `config/__init__.py`

```python
from .settings import ACCOUNT, CONTRACTS, ContractSpec, AccountLimits

```

## `config/settings.py`

```python
"""
T3 Trading Account Configuration
Hard constraints for the $10k prop account.
All systems must respect these values.
"""

from dataclasses import dataclass
from typing import Dict


@dataclass(frozen=True)
class ContractSpec:
    symbol: str
    multiplier: float          # $ per full point
    tick_size: float
    tick_value: float
    max_contracts: int         # firm position limit
    point_value_note: str


# Exact specs for the products we are allowed to trade
CONTRACTS: Dict[str, ContractSpec] = {
    "MES": ContractSpec(
        symbol="MES",
        multiplier=5.0,            # $5 per point
        tick_size=0.25,
        tick_value=1.25,
        max_contracts=10,          # 10 MES = 1 ES equivalent
        point_value_note="$5/pt → 10 contracts = $50/pt"
    ),
    "ES": ContractSpec(
        symbol="ES",
        multiplier=50.0,
        tick_size=0.25,
        tick_value=12.50,
        max_contracts=1,
        point_value_note="$50/pt"
    ),
    "MGC": ContractSpec(
        symbol="MGC",
        multiplier=10.0,           # $10 per $1 move in gold
        tick_size=0.10,
        tick_value=1.0,
        max_contracts=5,
        point_value_note="$10 per $1 → 5 contracts = $50 per $1"
    ),
    "SIL": ContractSpec(
        symbol="SIL",
        multiplier=1000.0,         # $1000 per $1 move in silver
        tick_size=0.005,
        tick_value=5.0,
        max_contracts=5,           # full size is extremely aggressive
        point_value_note="$1000 per $1 → 5 contracts = $5000 per $1"
    ),
}


@dataclass(frozen=True)
class AccountLimits:
    account_size: float = 10_000.0
    max_daily_loss: float = 750.0          # hard auto-liq
    soft_daily_loss: float = 500.0         # our internal circuit breaker
    max_planned_risk_per_day: float = 350.0  # target risk budget
    commission_per_contract: float = 0.50  # + exchange pass-throughs
    platform_monthly_fee: float = 574.0    # reduced by 150 if >3500 contracts/month
    profit_split_trader: float = 0.90


ACCOUNT = AccountLimits()


# Risk sizing defaults (can be overridden per strategy)
DEFAULT_RISK_PER_TRADE_PCT = 0.005   # 0.5% of account = $50
MAX_OPEN_RISK_PCT = 0.04             # 4% of account across all positions

```

## `data/__init__.py`

```python
"""Data loading and continuous-contract utilities."""

```

## `data/bars.py`

```python
"""
Bar resampling and session filters for the research / backtest path.
"""

from __future__ import annotations

import pandas as pd

from data.continuous import add_session_start


def resample_ohlcv(df: pd.DataFrame, rule: str = "5min") -> pd.DataFrame:
    """Resample OHLCV and rebuild session_start on the new index."""
    out = (
        df.resample(rule)
        .agg(
            {
                "open": "first",
                "high": "max",
                "low": "min",
                "close": "last",
                "volume": "sum",
            }
        )
        .dropna(subset=["open", "high", "low", "close"])
    )
    return add_session_start(out)


def filter_rth(
    df: pd.DataFrame,
    start: str = "09:30",
    end: str = "16:00",
    timezone: str = "America/New_York",
) -> pd.DataFrame:
    """Keep only Regular Trading Hours bars (inclusive start, exclusive end)."""
    idx = df.index
    if idx.tz is None:
        idx = idx.tz_localize(timezone)
    else:
        idx = idx.tz_convert(timezone)

    out = df.copy()
    out.index = idx
    times = out.index.strftime("%H:%M")
    mask = (times >= start) & (times < end)
    return out.loc[mask].copy()

```

## `data/continuous.py`

```python
"""
Continuous contract utilities.
Placeholder for the real data pipeline (Databento / Rithmic historical / CME DataMine).
"""

from __future__ import annotations
import pandas as pd
from pathlib import Path
from typing import Optional


def load_parquet(path: str | Path) -> pd.DataFrame:
    """
    Expected columns: datetime (index), open, high, low, close, volume
    Optional: session_start (bool)
    """
    df = pd.read_parquet(path)
    if not isinstance(df.index, pd.DatetimeIndex):
        if "datetime" in df.columns:
            df = df.set_index("datetime")
        else:
            raise ValueError("Data must have a DatetimeIndex or a 'datetime' column")
    df = df.sort_index()
    return df


def add_session_start(
    df: pd.DataFrame,
    session_open: str = "09:30",
    timezone: str = "America/New_York"
) -> pd.DataFrame:
    """
    Mark the first bar of each RTH session.
    Assumes the index is timezone-aware or will be localized.
    """
    df = df.copy()
    if df.index.tz is None:
        df.index = df.index.tz_localize(timezone)
    else:
        df.index = df.index.tz_convert(timezone)

    times = df.index.strftime("%H:%M")
    df["session_start"] = times == session_open
    # Also mark the first bar of the day if session_open is missing (e.g. overnight data)
    df["session_start"] = df["session_start"] | (df.index.to_series().diff() > pd.Timedelta("6h"))
    return df


def make_continuous_ratio(
    front: pd.DataFrame,
    next_contract: pd.DataFrame,
    roll_date: pd.Timestamp
) -> pd.DataFrame:
    """
    Simple ratio-adjusted continuous series.
    This is a minimal example – production code needs a full roll calendar.
    """
    # Placeholder – real implementation will use a roll schedule
    raise NotImplementedError("Full continuous-contract builder coming next")

```

## `data/databento_loader.py`

```python
"""
Databento continuous-contract loader for t3_quant.
Pulls MES / MGC / SIL continuous contracts and saves clean Parquet files
with the session_start column expected by the rest of the system.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Literal
from datetime import datetime, date

import pandas as pd
import databento as db
from dotenv import load_dotenv

from data.continuous import add_session_start

load_dotenv()  # reads .env

# Default location for cached Parquet files
DATA_DIR = Path(__file__).resolve().parent / "parquet"
DATA_DIR.mkdir(exist_ok=True)


def get_client() -> db.Historical:
    key = os.getenv("DATABENTO_API_KEY")
    if not key:
        raise ValueError("DATABENTO_API_KEY not found in environment or .env")
    return db.Historical(key)


def fetch_continuous(
    symbol: str = "MES",
    start: str | date | datetime = "2024-01-01",
    end: Optional[str | date | datetime] = None,
    schema: Literal["ohlcv-1s", "ohlcv-1m", "ohlcv-1h", "ohlcv-1d"] = "ohlcv-1m",
    roll: Literal["v", "n"] = "v",          # volume or open-interest
    front: int = 0,                         # 0 = front month
    save: bool = True,
) -> pd.DataFrame:
    """
    Fetch continuous contract data from Databento.

    Parameters
    ----------
    symbol : str
        Root symbol (MES, ES, MGC, SIL, ...)
    start, end : date-like
        Inclusive range. end=None → today
    schema : str
        Bar size
    roll : "v" | "n"
        Volume-based or open-interest-based continuous
    front : int
        0 = front month, 1 = second month, etc.
    save : bool
        Write Parquet to data/parquet/
    """
    client = get_client()

    continuous_symbol = f"{symbol}.{roll}.{front}"
    print(f"Requesting {continuous_symbol} | {schema} | {start} -> {end or 'now'}")

    data = client.timeseries.get_range(
        dataset="GLBX.MDP3",
        symbols=continuous_symbol,
        stype_in="continuous",
        schema=schema,
        start=start,
        end=end,
    )

    df = data.to_df()

    # Standardize column names and index
    if not isinstance(df.index, pd.DatetimeIndex):
        if "ts_event" in df.columns:
            df = df.set_index("ts_event")
        else:
            df.index = pd.to_datetime(df.index)

    df = df.sort_index()

    # Keep only the columns we need + rename if necessary
    keep = [c for c in ["open", "high", "low", "close", "volume"] if c in df.columns]
    df = df[keep].copy()

    # Add session_start flag (RTH 09:30 ET)
    df = add_session_start(df)

    if save:
        fname = f"{symbol}_{roll}{front}_{schema}_{start}_{end or 'latest'}.parquet"
        fname = fname.replace(":", "-").replace(" ", "_")
        path = DATA_DIR / fname
        df.to_parquet(path)
        print(f"Saved -> {path}  ({len(df):,} rows)")

    return df


def load_parquet(
    symbol: str = "MES",
    schema: str = "ohlcv-1m",
    roll: str = "v",
    front: int = 0,
) -> pd.DataFrame:
    """
    Load the most recent matching Parquet file for convenience.
    """
    pattern = f"{symbol}_{roll}{front}_{schema}_*.parquet"
    files = sorted(DATA_DIR.glob(pattern))
    if not files:
        raise FileNotFoundError(f"No Parquet found matching {pattern}")
    path = files[-1]
    print(f"Loading {path.name}")
    return pd.read_parquet(path)


# ------------------------------------------------------------------
# Quick CLI-style usage when run directly
# ------------------------------------------------------------------
if __name__ == "__main__":
    # Example: last ~6 months of 1-minute continuous MES
    df = fetch_continuous(
        symbol="MES",
        start="2025-02-01",
        end="2025-08-01",
        schema="ohlcv-1m",
        roll="v",
        front=0,
        save=True,
    )
    print(df.tail())
    print(f"\nSession starts found: {df['session_start'].sum()}")

```

## `example_usage.py`

```python
"""
Quick example of how the pieces fit together.
Replace the synthetic data with real continuous contracts once the data pipeline is live.
"""

import pandas as pd
import numpy as np
from risk import DailyRiskManager
from strategies import WeightedEnsembleStrategy
from backtest import SimpleBacktester
from data.continuous import add_session_start


def make_synthetic_mes(n_bars: int = 2000) -> pd.DataFrame:
    """Generate a simple random-walk series that looks roughly like MES."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01 09:30", periods=n_bars, freq="5min")
    # crude RTH filter
    dates = dates[(dates.time >= pd.Timestamp("09:30").time()) &
                  (dates.time <= pd.Timestamp("16:00").time())]

    returns = np.random.normal(0, 0.0008, len(dates))
    close = 5200 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.0004, len(dates))))
    low = close * (1 - np.abs(np.random.normal(0, 0.0004, len(dates))))
    open_ = close.copy()
    volume = np.random.randint(500, 5000, len(dates))

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)
    df = add_session_start(df)
    return df


if __name__ == "__main__":
    print("Building synthetic MES data...")
    data = make_synthetic_mes(1500)

    risk = DailyRiskManager()
    strategy = WeightedEnsembleStrategy(
        risk_manager=risk,
        use_adaptive_weights=True,
        min_accuracy=0.48,
        multi_tf_agreement=0.75,
        require_cpr_filter=False,   # no CPR on synthetic
        require_orb_filter=False,
    )

    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=6.0,
    )

    print("Running backtest (this is only a smoke test on synthetic data)...")
    result = bt.run(data)

    print(f"\nFinal PnL:     ${result.final_pnl:,.2f}")
    print(f"Max Drawdown:  ${result.max_dd:,.2f}")
    print(f"Trades:        {result.num_trades}")
    print(f"Locked days:   {result.locked_out_days}")
    print("\nScaffolding is ready. Open the t3_quant folder in Cursor and start iterating.")

```

## `features/__init__.py`

```python
from .indicators import *
from .multi_tf import multi_tf_alignment, higher_tf_trend
from .session_levels import cpr_levels_series

```

## `features/indicators.py`

```python
"""
Core technical features extracted from the TradingView ensemble indicator.
All functions are pure / vectorized where possible and return pandas Series.
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Tuple


def true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    prev_close = close.shift(1)
    tr = pd.concat([
        high - low,
        (high - prev_close).abs(),
        (low - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr


def atr(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 10) -> pd.Series:
    return true_range(high, low, close).rolling(period).mean()


def supertrend(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    period: int = 10,
    multiplier: float = 3.0
) -> Tuple[pd.Series, pd.Series]:
    """
    Returns (supertrend_line, direction)
    direction: +1 bullish, -1 bearish

    Path-dependent by design; implemented with NumPy arrays (not pandas .iloc
    in the hot loop) so research sweeps stay usable.
    """
    atr_val = atr(high, low, close, period).to_numpy(dtype=float)
    h = high.to_numpy(dtype=float)
    l = low.to_numpy(dtype=float)
    c = close.to_numpy(dtype=float)
    n = len(c)

    hl2 = (h + l) / 2.0
    upper = hl2 + multiplier * atr_val
    lower = hl2 - multiplier * atr_val

    direction = np.ones(n, dtype=float)
    st = np.full(n, np.nan, dtype=float)

    for i in range(1, n):
        if c[i] > upper[i - 1]:
            direction[i] = 1.0
        elif c[i] < lower[i - 1]:
            direction[i] = -1.0
        else:
            direction[i] = direction[i - 1]
            if direction[i] == 1.0 and lower[i] < lower[i - 1]:
                lower[i] = lower[i - 1]
            if direction[i] == -1.0 and upper[i] > upper[i - 1]:
                upper[i] = upper[i - 1]

        st[i] = lower[i] if direction[i] == 1.0 else upper[i]

    idx = close.index
    return pd.Series(st, index=idx, name="supertrend"), pd.Series(
        direction, index=idx, name="st_dir"
    )


def moving_average_signal(
    close: pd.Series,
    fast: int = 9,
    slow: int = 21
) -> pd.Series:
    """+1 when fast > slow, -1 otherwise."""
    ma_fast = close.rolling(fast).mean()
    ma_slow = close.rolling(slow).mean()
    return np.sign(ma_fast - ma_slow).fillna(0)


def session_vwap(
    high: pd.Series,
    low: pd.Series,
    close: pd.Series,
    volume: pd.Series,
    session_start_mask: pd.Series
) -> pd.Series:
    """
    Session VWAP. session_start_mask is True on the first bar of each session.
    For RTH futures this is typically the 09:30 ET bar.
    """
    typical = (high + low + close) / 3.0
    cum_tp_vol = (typical * volume).groupby(session_start_mask.cumsum()).cumsum()
    cum_vol = volume.groupby(session_start_mask.cumsum()).cumsum()
    return cum_tp_vol / cum_vol


def vwap_signal(close: pd.Series, vwap: pd.Series) -> pd.Series:
    """+1 price above VWAP, -1 below."""
    return np.sign(close - vwap).fillna(0)


def linear_regression_signal(
    close: pd.Series,
    window: int = 20
) -> Tuple[pd.Series, pd.Series]:
    """
    Returns (slope_signal, residual_zscore)
    slope_signal: +1 if regression slope > 0
    residual_zscore: standardized distance from the regression line
                     (useful for mean-reversion overlays)
    """
    def _linreg(y):
        x = np.arange(len(y))
        if len(y) < 2 or np.any(np.isnan(y)):
            return np.nan, np.nan
        slope, intercept = np.polyfit(x, y, 1)
        fitted = slope * x + intercept
        resid = y[-1] - fitted[-1]
        return slope, resid

    results = close.rolling(window).apply(lambda y: _linreg(y)[0], raw=True)
    residuals = close.rolling(window).apply(lambda y: _linreg(y)[1], raw=True)

    slope_signal = np.sign(results).fillna(0)
    resid_std = residuals.rolling(window).std()
    residual_z = (residuals / resid_std).fillna(0)

    return slope_signal, residual_z


def central_pivot_range(prev_high: float, prev_low: float, prev_close: float) -> dict:
    """
    Classic CPR levels for the current session.
    TC = Top Central, BC = Bottom Central, Pivot = central pivot.
    """
    pivot = (prev_high + prev_low + prev_close) / 3.0
    bc = (prev_high + prev_low) / 2.0
    tc = (pivot - bc) + pivot
    return {
        "pivot": pivot,
        "bc": bc,
        "tc": tc,
        "r1": 2 * pivot - prev_low,
        "s1": 2 * pivot - prev_high,
    }


def opening_range(
    high: pd.Series,
    low: pd.Series,
    open_: pd.Series,
    or_bars: int = 5
) -> Tuple[float, float]:
    """
    Simple opening-range high/low over the first `or_bars` of the session.
    Returns (or_high, or_low). Call once per session after the range is complete.
    """
    or_high = high.iloc[:or_bars].max()
    or_low = low.iloc[:or_bars].min()
    return or_high, or_low

```

## `features/multi_tf.py`

```python
"""
Multi-timeframe trend alignment filter.
Mirrors the 3m / 5m / 15m / 1h / 1d confluence panel from the TradingView indicator.
"""

from __future__ import annotations
import pandas as pd
import numpy as np
from typing import Dict, List


def higher_tf_trend(
    close: pd.Series,
    method: str = "ema",
    fast: int = 8,
    slow: int = 21
) -> pd.Series:
    """
    Simple trend direction on a single series.
    +1 bullish, -1 bearish, 0 neutral / insufficient data.
    """
    if method == "ema":
        f = close.ewm(span=fast, adjust=False).mean()
        s = close.ewm(span=slow, adjust=False).mean()
        return np.sign(f - s).fillna(0)
    else:
        # fallback: linear regression slope sign
        def slope_sign(y):
            if len(y) < slow or np.any(np.isnan(y)):
                return 0.0
            x = np.arange(len(y))
            slope = np.polyfit(x, y, 1)[0]
            return np.sign(slope)
        return close.rolling(slow).apply(slope_sign, raw=True).fillna(0)


def multi_tf_alignment(
    tf_closes: Dict[str, pd.Series],
    required_agreement: float = 1.0
) -> pd.Series:
    """
    tf_closes: dict of {timeframe_name: close_series}
               e.g. {"5m": df_5m.close, "15m": df_15m.close, "1h": ..., "1d": ...}

    Returns a Series (indexed to the lowest TF) that is True only when
    the fraction of higher timeframes that agree on direction >= required_agreement.

    Typical usage for the T3 account:
        required_agreement = 0.75  (at least 3 out of 4 higher TFs agree)
        or 1.0 for the strict “all must align” behaviour of the original indicator.
    """
    if not tf_closes:
        raise ValueError("tf_closes must contain at least one series")

    # Use the shortest timeframe as the master index
    master_name = min(tf_closes.keys(), key=lambda k: len(tf_closes[k]))
    master = tf_closes[master_name]
    master_idx = master.index

    directions = {}
    for name, series in tf_closes.items():
        dir_ = higher_tf_trend(series)
        # Align to master index (forward-fill higher TF values)
        directions[name] = dir_.reindex(master_idx, method="ffill").fillna(0)

    dir_df = pd.DataFrame(directions)
    # Count how many are bullish / bearish
    bull_count = (dir_df > 0).sum(axis=1)
    bear_count = (dir_df < 0).sum(axis=1)
    total = len(tf_closes)

    alignment = pd.Series(0, index=master_idx)
    alignment[bull_count / total >= required_agreement] = 1
    alignment[bear_count / total >= required_agreement] = -1

    return alignment

```

## `features/session_levels.py`

```python
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

```

## `requirements.txt`

```text
numpy>=1.26
pandas>=2.2
databento>=0.83
python-dotenv>=1.0
pyarrow>=13.0
plotly>=6.0
jupyter>=1.0

```

## `risk/__init__.py`

```python
from .daily_risk_manager import DailyRiskManager, PositionState

```

## `risk/daily_risk_manager.py`

```python
"""
DailyRiskManager V2
Hard guarantee: equity can never print worse than -hard_loss_limit
when marks are supplied on every bar extreme.

Policy (explicit):
- Soft lock (-$500): block new risk for the rest of the day. Do NOT force-flatten.
  Existing positions keep their stops. No intraday unlock/recovery.
- Hard lock (-$750): force-flatten immediately at the provided mark prices.
- Overnight holds are undefined: the system assumes RTH-flat.
  reset_day() clears state without realizing gaps — callers must be flat first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import date
import logging

from config.settings import ACCOUNT, CONTRACTS

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    symbol: str
    qty: int  # signed
    avg_price: float
    unrealized_pnl: float = 0.0


@dataclass
class DailyRiskManager:
    soft_loss_limit: float = ACCOUNT.soft_daily_loss  # 500
    hard_loss_limit: float = ACCOUNT.max_daily_loss  # 750
    max_planned_risk: float = ACCOUNT.max_planned_risk_per_day
    commission_per_side: float = ACCOUNT.commission_per_contract

    current_date: Optional[date] = None
    realized_pnl: float = 0.0
    open_positions: Dict[str, PositionState] = field(default_factory=dict)
    is_locked: bool = False
    lock_reason: str = ""
    worst_pnl_today: float = 0.0  # most negative equity seen today

    # ------------------------------------------------------------------
    # Day management
    # ------------------------------------------------------------------
    def reset_day(self, today: date) -> None:
        if self.current_date != today:
            if self.open_positions:
                logger.error(
                    "reset_day called with open positions — overnight/gap PnL is undefined. "
                    "Flatten before day rollover."
                )
            self.current_date = today
            self.realized_pnl = 0.0
            self.open_positions.clear()
            self.is_locked = False
            self.lock_reason = ""
            self.worst_pnl_today = 0.0
            logger.info(f"Risk manager reset for {today}")

    # ------------------------------------------------------------------
    # Core state
    # ------------------------------------------------------------------
    @property
    def total_pnl(self) -> float:
        unrealized = sum(p.unrealized_pnl for p in self.open_positions.values())
        return self.realized_pnl + unrealized

    @property
    def remaining_risk_budget(self) -> float:
        """Remaining room before soft lock."""
        return max(0.0, self.soft_loss_limit + self.total_pnl)

    def _update_worst(self) -> None:
        self.worst_pnl_today = min(self.worst_pnl_today, self.total_pnl)

    def _charge_commission(self, qty: int) -> None:
        self.realized_pnl -= abs(qty) * self.commission_per_side

    # ------------------------------------------------------------------
    # Marking & limit enforcement
    # ------------------------------------------------------------------
    def update_unrealized(self, symbol: str, mark_price: float) -> None:
        """Update mark and immediately enforce limits."""
        if symbol not in self.open_positions:
            return
        pos = self.open_positions[symbol]
        spec = CONTRACTS[symbol]
        direction = 1 if pos.qty > 0 else -1
        points = (mark_price - pos.avg_price) * direction
        pos.unrealized_pnl = points * abs(pos.qty) * spec.multiplier
        self._check_and_enforce(mark_prices={symbol: mark_price})

    def mark_all_and_check(self, marks: Dict[str, float]) -> None:
        """Convenience: update every open position and enforce."""
        for sym, px in marks.items():
            if sym in self.open_positions:
                self.update_unrealized(sym, px)

    def _limit_flatten_price(self, symbol: str, pos: PositionState) -> float:
        """
        Price that closes this position so post-commission realized PnL lands
        on -hard_loss_limit (single-position case used by the MES backtester).
        """
        spec = CONTRACTS[symbol]
        commission = abs(pos.qty) * self.commission_per_side
        # After flatten: realized_old + trade_pnl - commission == -hard_loss_limit
        trade_pnl = -self.hard_loss_limit - self.realized_pnl + commission
        points = trade_pnl / (abs(pos.qty) * spec.multiplier)
        if pos.qty > 0:
            return pos.avg_price + points
        return pos.avg_price - points

    def _capped_flatten_marks(self, mark_prices: Dict[str, float]) -> Dict[str, float]:
        """Do not realize beyond the hard limit when the bar extreme overshoots."""
        capped: Dict[str, float] = {}
        for sym, pos in self.open_positions.items():
            if sym not in mark_prices:
                raise ValueError(
                    f"Cannot force-flatten {sym} without a mark price "
                    "(refusing to realize at avg_price / $0 phantom PnL)"
                )
            raw = mark_prices[sym]
            limit_px = self._limit_flatten_price(sym, pos)
            # Longs: adverse is lower → flatten at the higher of raw vs limit
            # Shorts: adverse is higher → flatten at the lower of raw vs limit
            capped[sym] = max(raw, limit_px) if pos.qty > 0 else min(raw, limit_px)
        return capped

    def _check_and_enforce(self, mark_prices: Optional[Dict[str, float]] = None) -> None:
        """
        Single place that can lock and force flatten.
        Called after every fill and every mark.

        Note: when a bar extreme would print past the hard limit, we flatten at the
        capped limit price and only then update worst_pnl_today — so a phantom
        intrabar mark beyond -$750 is never recorded as realized equity.
        """
        total = self.total_pnl

        if total <= -self.hard_loss_limit:
            self.lock_reason = f"HARD LIMIT: {total:.2f} <= -{self.hard_loss_limit}"
            logger.critical(self.lock_reason)
            capped = self._capped_flatten_marks(mark_prices or {})
            self._force_flatten(capped)
            self.is_locked = True
            self._update_worst()
            return

        self._update_worst()

        if total <= -self.soft_loss_limit and not self.is_locked:
            # Policy: soft lock is permanent for the session day (no recovery unlock).
            self.lock_reason = f"SOFT LIMIT: {total:.2f} <= -{self.soft_loss_limit}"
            logger.warning(self.lock_reason)
            self.is_locked = True

    def _force_flatten(self, mark_prices: Dict[str, float]) -> None:
        """Realize every open position at the provided marks. Marks are required."""
        for sym in list(self.open_positions.keys()):
            if sym not in mark_prices:
                raise ValueError(
                    f"Cannot force-flatten {sym} without a mark price "
                    "(refusing to realize at avg_price / $0 phantom PnL)"
                )
            pos = self.open_positions[sym]
            px = mark_prices[sym]
            direction = 1 if pos.qty > 0 else -1
            points = (px - pos.avg_price) * direction
            realized = points * abs(pos.qty) * CONTRACTS[sym].multiplier
            self.realized_pnl += realized
            self._charge_commission(pos.qty)  # closing side
            logger.warning(
                f"Forced flatten {sym} qty={pos.qty} @ {px:.2f} -> {realized:.2f}"
            )
            del self.open_positions[sym]

    # ------------------------------------------------------------------
    # Fills
    # ------------------------------------------------------------------
    def record_fill(
        self, symbol: str, qty: int, price: float, is_closing: bool = False
    ) -> None:
        """
        qty signed (+ buy / - sell).
        After every fill we re-check limits.
        """
        if symbol not in self.open_positions:
            self.open_positions[symbol] = PositionState(
                symbol=symbol, qty=0, avg_price=price
            )

        pos = self.open_positions[symbol]
        spec = CONTRACTS[symbol]

        # Closing or reversing
        if is_closing or (pos.qty != 0 and (pos.qty > 0) != (qty > 0)):
            closed_qty = min(abs(pos.qty), abs(qty))
            direction = 1 if pos.qty > 0 else -1
            points = (price - pos.avg_price) * direction
            realized = points * closed_qty * spec.multiplier
            self.realized_pnl += realized

            if abs(qty) >= abs(pos.qty):
                remaining = pos.qty + qty
                if remaining == 0:
                    del self.open_positions[symbol]
                else:
                    pos.qty = remaining
                    pos.avg_price = price
                    pos.unrealized_pnl = 0.0
            else:
                pos.qty += qty
                pos.unrealized_pnl = 0.0
        else:
            # Adding
            new_qty = pos.qty + qty
            if pos.qty == 0:
                pos.avg_price = price
            else:
                pos.avg_price = (
                    pos.avg_price * abs(pos.qty) + price * abs(qty)
                ) / abs(new_qty)
            pos.qty = new_qty

        self._charge_commission(qty)
        self._check_and_enforce(mark_prices={symbol: price})

    # ------------------------------------------------------------------
    # Permission & sizing
    # ------------------------------------------------------------------
    def can_take_new_risk(self) -> bool:
        return not self.is_locked

    def recommend_size(
        self,
        symbol: str,
        stop_points: float,
        risk_dollars: Optional[float] = None,
    ) -> int:
        if not self.can_take_new_risk():
            return 0

        spec = CONTRACTS[symbol]
        if risk_dollars is None:
            risk_dollars = min(
                ACCOUNT.account_size * 0.005,
                self.remaining_risk_budget * 0.5,  # more conservative buffer
                self.max_planned_risk * 0.4,
            )

        if stop_points <= 0:
            return 0

        risk_per_contract = stop_points * spec.multiplier
        size = int(risk_dollars // risk_per_contract)
        size = max(0, min(size, spec.max_contracts))

        # Extra SIL protection — 1 contract until proven
        if symbol == "SIL" and size > 1 and stop_points > 0.08:
            size = min(size, 1)

        return size

    def flatten_all(self, mark_prices: Optional[Dict[str, float]] = None) -> None:
        """Public emergency flatten — requires marks for any open symbols."""
        marks = mark_prices or {}
        self._force_flatten(marks)
        self.is_locked = True
        self.lock_reason = self.lock_reason or "Manual / emergency flatten"
        self._update_worst()

```

## `scripts/export_share_pack.py`

```python
"""
Build SHARE_PACK.md — handoff + all source files for pasting into another agent.

Excludes secrets, parquet, caches, and generated outputs.

Usage:
  python scripts/export_share_pack.py
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "SHARE_PACK.md"

SKIP_DIR_NAMES = {
    ".git",
    ".venv",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".ipynb_checkpoints",
    "parquet",
}

SKIP_FILES = {
    ".env",
    "SHARE_PACK.md",
}

# Include research metrics/summaries; skip bulky trade/equity CSVs
INCLUDE_SUFFIXES = {".py", ".txt", ".md", ".gitignore", ".csv"}
INCLUDE_CSV_NAMES = {
    "v1_ablation_summary.csv",
    "v1_tighten_summary.csv",
    "v1_regime_summary.csv",
    "regime_spec_summary.csv",
    "regime_15m_summary.csv",
}


def should_skip(path: Path) -> bool:
    rel = path.as_posix() if not path.is_absolute() else path.name
    name = path.name
    if name in SKIP_FILES:
        return True
    if path.suffix == ".parquet":
        return True
    for part in path.parts:
        if part in SKIP_DIR_NAMES:
            return True
    if path.suffix == ".csv":
        # Keep summary tables only (not every trade blotter)
        if name not in INCLUDE_CSV_NAMES and "summary" not in name:
            return True
    return False


def main() -> None:
    chunks: list[str] = []
    handoff = ROOT / "HANDOFF.md"
    if handoff.exists():
        chunks.append(handoff.read_text(encoding="utf-8"))
        chunks.append("\n\n---\n\n# Source dump\n\n")

    files = sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not should_skip(p.relative_to(ROOT))
        and (p.suffix in INCLUDE_SUFFIXES or p.name == ".gitignore")
    )

    for path in files:
        rel = path.relative_to(ROOT).as_posix()
        if rel == "HANDOFF.md":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        lang = "python" if path.suffix == ".py" else "text"
        chunks.append(f"## `{rel}`\n\n```{lang}\n{text}\n```\n\n")

    OUT.write_text("".join(chunks), encoding="utf-8")
    size_kb = OUT.stat().st_size / 1024
    print(f"Wrote {OUT} ({size_kb:.1f} KB, {len(files)} files)")
    print("Includes: all .py source, HANDOFF, metrics .txt, summary CSVs")
    print("Excluded: .env, parquet market data, per-trade equity CSVs")


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    main()

```

## `scripts/pull_mes_long_history.py`

```python
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

```

## `strategies/__init__.py`

```python
from .base import StrategyBase
from .weighted_ensemble import WeightedEnsembleStrategy
from .tight_ensemble import TightenedEnsembleStrategy
from .supertrend_regime import SuperTrendRegimeStrategy
from .entry_filters import tighten_entries

```

## `strategies/base.py`

```python
"""
StrategyBase – common interface for every system we build.
"""

from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any
import pandas as pd

from risk.daily_risk_manager import DailyRiskManager


class StrategyBase(ABC):
    """
    All strategies must implement generate_signals and respect the risk manager.
    """

    def __init__(self, name: str, risk_manager: DailyRiskManager):
        self.name = name
        self.risk = risk_manager
        self.params: Dict[str, Any] = {}

    @abstractmethod
    def generate_signals(self, data: pd.DataFrame) -> pd.Series:
        """
        Return a Series of target position direction:
            +1 long, -1 short, 0 flat
        Indexed the same as data.
        """
        pass

    def size_position(
        self,
        symbol: str,
        signal: int,
        stop_points: float,
        data: Optional[pd.DataFrame] = None
    ) -> int:
        """
        Convert a directional signal into a contract quantity
        that respects the DailyRiskManager.
        """
        if signal == 0 or not self.risk.can_take_new_risk():
            return 0
        size = self.risk.recommend_size(symbol, stop_points)
        return size * signal   # signed quantity

    def on_bar(self, bar: pd.Series, data: pd.DataFrame) -> Dict[str, Any]:
        """
        Optional hook for live / event-driven use.
        Returns a dict that may contain 'order' instructions.
        """
        return {}

```

## `strategies/entry_filters.py`

```python
"""
Entry tightening filters for the MTF-gated ensemble.

Applied *after* raw directional signals so we can compare baseline vs tightened
without rewriting indicator math.
"""

from __future__ import annotations

import numpy as np
import pandas as pd


def tighten_entries(
    raw_direction: pd.Series,
    close: pd.Series,
    vwap: pd.Series,
    *,
    entry_start: str = "10:00",
    entry_end: str = "11:30",
    require_pullback: bool = True,
    cooldown_bars: int = 6,
    flatten_outside_window: bool = True,
) -> pd.Series:
    """
    Convert a raw ±1/0 series into a tighter target series.

    Rules:
      - New entries only inside [entry_start, entry_end) ET.
      - Optional pullback: long only if close <= VWAP; short if close >= VWAP.
      - Cooldown bars after any exit before a new entry.
      - If flatten_outside_window: force flat outside the entry window
        (matches defensive midday / no overnight style ops).
    """
    if len(raw_direction) == 0:
        return raw_direction.copy()

    idx = raw_direction.index
    times = pd.Index(idx.strftime("%H:%M"))
    out = np.zeros(len(raw_direction), dtype=float)
    state = 0
    cooldown = 0

    for i in range(len(raw_direction)):
        d = float(raw_direction.iloc[i])
        t = times[i]
        in_window = entry_start <= t < entry_end

        if cooldown > 0:
            cooldown -= 1

        if state != 0:
            # Exit if raw flips/flats, or session window ends
            leave = d == 0 or np.sign(d) != np.sign(state)
            if flatten_outside_window and not in_window:
                leave = True
            if leave:
                state = 0
                cooldown = cooldown_bars
            out[i] = state
            continue

        # Flat — consider entry
        if d == 0 or not in_window or cooldown > 0:
            out[i] = 0
            continue

        if require_pullback:
            px = float(close.iloc[i])
            v = float(vwap.iloc[i]) if np.isfinite(vwap.iloc[i]) else np.nan
            if np.isnan(v):
                out[i] = 0
                continue
            if d > 0 and px > v:
                out[i] = 0
                continue
            if d < 0 and px < v:
                out[i] = 0
                continue

        state = int(np.sign(d))
        out[i] = state

    return pd.Series(out, index=idx, name="tight_direction")

```

## `strategies/supertrend_regime.py`

```python
"""
SuperTrendRegimeStrategy
Single-regime directional strategy replacing the 4-way ensemble.

Theory of operation:
  - Regime: 15-min SuperTrend sets the ONLY directional input.
  - Entry: optional pullback to session VWAP within the regime.
  - Permission: optional MTF gate (15m + 1h, >=75%).
  - Exit: regime flips / chop, or fixed stop (backtester).

Note: Our SimpleBacktester treats the signal as a *continuous target*
(+1 hold long / -1 hold short / 0 flat). Entry pulses alone would
flatten on the next bar, so this implementation enters on setup and
*holds* while the regime remains valid.
"""

from __future__ import annotations

from typing import Dict, Optional

import numpy as np
import pandas as pd

from features.indicators import session_vwap, supertrend
from features.multi_tf import multi_tf_alignment
from risk.daily_risk_manager import DailyRiskManager
from strategies.base import StrategyBase


class SuperTrendRegimeStrategy(StrategyBase):
    """
    Regime: 15-min SuperTrend (10, 3.0)
    Entry: 5-min pullback to session VWAP within regime (optional)
    Permission: MTF gate (optional)
    Exit: Regime flip/chop (signal -> 0) or stop (backtester)
    """

    def __init__(
        self,
        risk_manager: DailyRiskManager,
        st_period: int = 10,
        st_multiplier: float = 3.0,
        min_regime_bars: int = 3,
        entry_window_start: str = "10:00",
        entry_window_end: str = "11:30",
        cooldown_bars: int = 6,
        require_pullback: bool = True,
        use_mtf: bool = True,
        multi_tf_agreement: float = 0.75,
        flatten_outside_window: bool = True,
    ):
        super().__init__("SuperTrendRegime", risk_manager)
        self.st_period = st_period
        self.st_multiplier = st_multiplier
        self.min_regime_bars = min_regime_bars
        self.entry_start = entry_window_start
        self.entry_end = entry_window_end
        self.cooldown_bars = cooldown_bars
        self.require_pullback = require_pullback
        self.use_mtf = use_mtf
        self.multi_tf_agreement = multi_tf_agreement
        self.flatten_outside_window = flatten_outside_window

    def _fifteen_min_regime(self, data: pd.DataFrame) -> pd.Series:
        resampled = (
            data.resample("15min")
            .agg({"high": "max", "low": "min", "close": "last"})
            .dropna()
        )
        _, st_dir = supertrend(
            resampled["high"],
            resampled["low"],
            resampled["close"],
            period=self.st_period,
            multiplier=self.st_multiplier,
        )
        st_dir = st_dir.astype(float)

        # Persist on *native* 15m bars, then map to 5m
        vals = st_dir.to_numpy(dtype=float)
        out = np.zeros(len(vals), dtype=float)
        run = 0
        prev = 0.0
        for i, v in enumerate(vals):
            if v == 0.0:
                run = 0
                prev = 0.0
                continue
            if v == prev:
                run += 1
            else:
                run = 1
                prev = v
            out[i] = v if run >= self.min_regime_bars else 0.0

        persisted = pd.Series(out, index=st_dir.index)
        return persisted.reindex(data.index, method="ffill").fillna(0.0)

    def generate_signals(
        self,
        data: pd.DataFrame,
        higher_tf_closes: Optional[Dict[str, pd.Series]] = None,
        cpr_levels: Optional[dict] = None,
        orb_high: Optional[float] = None,
        orb_low: Optional[float] = None,
    ) -> pd.Series:
        # 1) Regime
        regime = self._fifteen_min_regime(data)

        # 2) Value level
        volume = data["volume"] if "volume" in data.columns else pd.Series(1.0, index=data.index)
        session_start = (
            data["session_start"]
            if "session_start" in data.columns
            else pd.Series(False, index=data.index)
        )
        vwap = session_vwap(
            data["high"], data["low"], data["close"], volume, session_start
        )

        close = data["close"].to_numpy(dtype=float)
        low = data["low"].to_numpy(dtype=float)
        high = data["high"].to_numpy(dtype=float)
        vwap_a = vwap.to_numpy(dtype=float)
        regime_a = regime.to_numpy(dtype=float)
        times = data.index.strftime("%H:%M")

        # Optional MTF series (permission applied at entry and for hold)
        if self.use_mtf and higher_tf_closes is not None:
            mtf = multi_tf_alignment(
                higher_tf_closes, required_agreement=self.multi_tf_agreement
            )
            mtf_a = mtf.reindex(data.index, method="ffill").fillna(0.0).to_numpy(dtype=float)
        else:
            mtf_a = None

        out = np.zeros(len(data), dtype=float)
        state = 0.0
        cooldown = 0

        for i in range(len(data)):
            r = regime_a[i]
            in_window = self.entry_start <= times[i] < self.entry_end

            if cooldown > 0:
                cooldown -= 1

            # Permission: when MTF is on, regime must match MTF
            permitted = True
            if mtf_a is not None:
                permitted = r != 0.0 and r == mtf_a[i]
                if not permitted:
                    r = 0.0

            # ----- Hold / exit -----
            if state != 0.0:
                leave = r == 0.0 or np.sign(r) != np.sign(state)
                if self.flatten_outside_window and not in_window:
                    leave = True
                if leave:
                    state = 0.0
                    cooldown = self.cooldown_bars
                out[i] = state
                continue

            # ----- Flat: entry -----
            if r == 0.0 or not in_window or cooldown > 0:
                out[i] = 0.0
                continue

            if self.require_pullback:
                v = vwap_a[i]
                if not np.isfinite(v):
                    out[i] = 0.0
                    continue
                # Spec: touch VWAP AND close on value side of VWAP
                long_setup = (r > 0) and (low[i] <= v) and (close[i] <= v)
                short_setup = (r < 0) and (high[i] >= v) and (close[i] >= v)
                if not (long_setup or short_setup):
                    out[i] = 0.0
                    continue

            state = float(np.sign(r))
            out[i] = state

        return pd.Series(out, index=data.index, name="st_regime_signal")

```

## `strategies/tight_ensemble.py`

```python
"""
MTF-gated equal-weight ensemble with entry tightening (V1.1 research sleeve).
"""

from __future__ import annotations

from typing import Dict, Optional

import pandas as pd

from features.indicators import session_vwap
from risk.daily_risk_manager import DailyRiskManager
from strategies.entry_filters import tighten_entries
from strategies.weighted_ensemble import WeightedEnsembleStrategy


class TightenedEnsembleStrategy(WeightedEnsembleStrategy):
    """
    Same core signals as WeightedEnsembleStrategy, plus:
      - RTH entry window (default 10:00–11:30)
      - VWAP pullback confirmation
      - Cooldown after exits
    """

    def __init__(
        self,
        risk_manager: DailyRiskManager,
        entry_start: str = "10:00",
        entry_end: str = "11:30",
        require_pullback: bool = True,
        cooldown_bars: int = 6,
        flatten_outside_window: bool = True,
        **kwargs,
    ):
        super().__init__(risk_manager=risk_manager, **kwargs)
        self.name = "TightenedEnsemble"
        self.entry_start = entry_start
        self.entry_end = entry_end
        self.require_pullback = require_pullback
        self.cooldown_bars = cooldown_bars
        self.flatten_outside_window = flatten_outside_window

    def generate_signals(
        self,
        data: pd.DataFrame,
        higher_tf_closes: Optional[Dict[str, pd.Series]] = None,
        cpr_levels: Optional[dict] = None,
        orb_high: Optional[float] = None,
        orb_low: Optional[float] = None,
    ) -> pd.Series:
        raw = super().generate_signals(
            data,
            higher_tf_closes=higher_tf_closes,
            cpr_levels=cpr_levels,
            orb_high=orb_high,
            orb_low=orb_low,
        )
        vwap = session_vwap(
            data["high"],
            data["low"],
            data["close"],
            data["volume"],
            data["session_start"],
        )
        return tighten_entries(
            raw,
            data["close"],
            vwap,
            entry_start=self.entry_start,
            entry_end=self.entry_end,
            require_pullback=self.require_pullback,
            cooldown_bars=self.cooldown_bars,
            flatten_outside_window=self.flatten_outside_window,
        )

```

## `strategies/weighted_ensemble.py`

```python
"""
WeightedEnsembleStrategy
Re-implementation of the TradingView multi-indicator ensemble
with proper quantitative hygiene for the T3 prop account.

Key differences from the original indicator:
- Hard accuracy gate (auto-disable on low accuracy)
- Online weight update is regularized and optional
- All signals still have to pass the DailyRiskManager
- Multi-TF filter is a hard permission layer, not just a display
- CPR / ORB used as explicit entry filters
"""

from __future__ import annotations
import numpy as np
import pandas as pd
from typing import Dict, Optional, List
from collections import deque

from strategies.base import StrategyBase
from risk.daily_risk_manager import DailyRiskManager
from features.indicators import (
    supertrend, moving_average_signal, vwap_signal,
    linear_regression_signal, session_vwap
)
from features.multi_tf import multi_tf_alignment


class WeightedEnsembleStrategy(StrategyBase):
    def __init__(
        self,
        risk_manager: DailyRiskManager,
        use_adaptive_weights: bool = True,
        learning_rate: float = 0.1,
        lookback: int = 100,
        min_accuracy: float = 0.48,          # hard gate – below this we go flat
        multi_tf_agreement: float = 0.75,    # 75% of higher TFs must agree
        require_cpr_filter: bool = True,
        require_orb_filter: bool = False,
    ):
        super().__init__("WeightedEnsemble", risk_manager)
        self.use_adaptive = use_adaptive_weights
        self.lr = learning_rate
        self.lookback = lookback
        self.min_accuracy = min_accuracy
        self.mtf_agreement = multi_tf_agreement
        self.require_cpr = require_cpr_filter
        self.require_orb = require_orb_filter

        # Equal-weight start (matches the “EQUAL WT” baseline in the screenshot)
        self.weights = {
            "supertrend": 0.25,
            "ma": 0.25,
            "vwap": 0.25,
            "linreg": 0.25,
        }

        # Online performance tracking (for adaptive weights + accuracy gate)
        self.signal_history: Dict[str, deque] = {
            k: deque(maxlen=lookback) for k in self.weights
        }
        self.outcome_history: deque = deque(maxlen=lookback)
        self.current_accuracy: float = 0.5
        self.is_enabled: bool = True

    def _update_weights(self, outcomes: Dict[str, float]) -> None:
        """
        Simple multiplicative-weights style update.
        outcomes[signal_name] = +1 if that signal was correct on the last bar, else -1.
        """
        if not self.use_adaptive:
            return

        for name, correct in outcomes.items():
            # Multiplicative update with learning rate
            self.weights[name] *= np.exp(self.lr * correct)
            self.signal_history[name].append(correct)

        # Renormalize
        total = sum(self.weights.values())
        if total > 0:
            for k in self.weights:
                self.weights[k] /= total

        # Update accuracy estimate
        if self.outcome_history:
            self.current_accuracy = np.mean(self.outcome_history)
            if self.current_accuracy < self.min_accuracy:
                self.is_enabled = False
            else:
                self.is_enabled = True

    def generate_signals(
        self,
        data: pd.DataFrame,
        higher_tf_closes: Optional[Dict[str, pd.Series]] = None,
        cpr_levels: Optional[dict] = None,
        orb_high: Optional[float] = None,
        orb_low: Optional[float] = None,
    ) -> pd.Series:
        """
        data must contain: high, low, close, volume
        and a boolean column 'session_start' marking the first bar of each RTH session.

        Returns target direction Series (+1 / -1 / 0)
        """
        if not self.is_enabled:
            return pd.Series(0, index=data.index)

        # ----- Individual signals -----
        _, st_dir = supertrend(data["high"], data["low"], data["close"])
        ma_dir = moving_average_signal(data["close"])
        vwap = session_vwap(
            data["high"], data["low"], data["close"], data["volume"],
            data["session_start"]
        )
        vwap_dir = vwap_signal(data["close"], vwap)
        linreg_dir, _ = linear_regression_signal(data["close"])

        signals = pd.DataFrame({
            "supertrend": st_dir,
            "ma": ma_dir,
            "vwap": vwap_dir,
            "linreg": linreg_dir,
        })

        # Weighted vote
        raw_score = (
            signals["supertrend"] * self.weights["supertrend"] +
            signals["ma"] * self.weights["ma"] +
            signals["vwap"] * self.weights["vwap"] +
            signals["linreg"] * self.weights["linreg"]
        )

        direction = np.sign(raw_score).fillna(0)

        # ----- Multi-TF permission filter -----
        if higher_tf_closes is not None:
            mtf = multi_tf_alignment(higher_tf_closes, self.mtf_agreement)
            mtf = mtf.reindex(data.index, method="ffill").fillna(0)
            # Only keep the signal when it agrees with the multi-TF regime
            direction = direction.where(direction == mtf, 0)

        # ----- CPR filter -----
        if self.require_cpr and cpr_levels is not None:
            # Accept a single-session dict OR a bar-aligned DataFrame/dict of Series
            if isinstance(cpr_levels, pd.DataFrame):
                tc = cpr_levels["tc"].reindex(data.index)
                bc = cpr_levels["bc"].reindex(data.index)
            elif isinstance(cpr_levels, dict) and any(
                isinstance(v, pd.Series) for v in cpr_levels.values()
            ):
                tc = pd.Series(cpr_levels["tc"]).reindex(data.index)
                bc = pd.Series(cpr_levels["bc"]).reindex(data.index)
            else:
                tc = cpr_levels["tc"]
                bc = cpr_levels["bc"]

            above_tc = data["close"] > tc
            below_bc = data["close"] < bc
            valid = tc.notna() & bc.notna() if hasattr(tc, "notna") else True
            direction = direction.where(valid, 0)
            # Long only above TC, short only below BC
            direction = direction.where(
                ((direction > 0) & above_tc) | ((direction < 0) & below_bc),
                0
            )

        # ----- ORB filter (optional) -----
        if self.require_orb and orb_high is not None and orb_low is not None:
            above_orh = data["close"] > orb_high
            below_orl = data["close"] < orb_low
            direction = direction.where(
                ((direction > 0) & above_orh) | ((direction < 0) & below_orl),
                0
            )

        return direction

    def record_outcome(self, signal_name: str, was_correct: bool) -> None:
        """Call after the fact to update adaptive weights and accuracy."""
        val = 1.0 if was_correct else -1.0
        self.outcome_history.append(1.0 if was_correct else 0.0)
        self._update_weights({signal_name: val})

```

## `test_databento.py`

```python
"""One-off Databento connection smoke test. Key comes from .env — never hard-code."""

import databento as db
from dotenv import load_dotenv

load_dotenv()

client = db.Historical()  # reads DATABENTO_API_KEY from environment

# Pull 5 days of continuous front-month MES (volume-based roll) as 1-minute bars
data = client.timeseries.get_range(
    dataset="GLBX.MDP3",  # CME Globex
    symbols="MES.v.0",  # continuous front month (volume roll)
    stype_in="continuous",
    schema="ohlcv-1m",  # 1-minute OHLCV
    start="2025-07-01",
    end="2025-07-05",
)

df = data.to_df()
print(df.head(20))
print(f"\nShape: {df.shape}")
print(f"Columns: {list(df.columns)}")

```

## `tests/test_backtester_adverse.py`

```python
"""Backtester must feed adverse extremes and never print past hard limit."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backtest.engine import SimpleBacktester
from risk.daily_risk_manager import DailyRiskManager
from strategies.base import StrategyBase


class AlwaysLong(StrategyBase):
    def __init__(self, risk_manager):
        super().__init__("AlwaysLong", risk_manager)

    def generate_signals(self, data, **kwargs):
        return pd.Series(1, index=data.index)


def _bars() -> pd.DataFrame:
    idx = pd.date_range("2025-06-02 09:30", periods=4, freq="5min", tz="America/New_York")
    # Bar 0: enter around 5000
    # Bar 1: catastrophic low that would be -$1000+ on 10 MES without capping
    return pd.DataFrame(
        {
            "open": [5000.0, 5000.0, 4980.0, 4985.0],
            "high": [5002.0, 5001.0, 4985.0, 4990.0],
            "low": [4998.0, 4800.0, 4975.0, 4980.0],  # 200pt air-pocket
            "close": [5000.0, 4985.0, 4982.0, 4988.0],
            "volume": [1000, 1000, 1000, 1000],
            "session_start": [True, False, False, False],
        },
        index=idx,
    )


def test_adverse_bar_cannot_print_past_hard_limit():
    risk = DailyRiskManager()
    strategy = AlwaysLong(risk)
    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=6.0,
        slippage_ticks=0.0,
    )
    result = bt.run(_bars())

    assert result.worst_intraday >= -risk.hard_loss_limit - 1e-6
    assert result.worst_intraday_pnl >= -risk.hard_loss_limit - 1e-6
    # Equity path also never prints past hard limit
    assert float(result.equity_curve.min()) >= -risk.hard_loss_limit - 1e-6


if __name__ == "__main__":
    test_adverse_bar_cannot_print_past_hard_limit()
    print("Backtester adverse-bar hard-limit test passed.")

```

## `tests/test_risk_hard_limit.py`

```python
"""Adversarial checks: hard daily loss cannot print past the limit."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk.daily_risk_manager import DailyRiskManager


def test_hard_limit_caps_adverse_mark():
    risk = DailyRiskManager()
    risk.reset_day(date(2025, 6, 1))

    # 10 MES @ $5/pt → 20-point adverse move = -$1,000 before hardening
    risk.record_fill("MES", 10, 5000.0)
    risk.update_unrealized("MES", 4980.0)

    assert risk.is_locked
    assert "HARD" in risk.lock_reason
    assert risk.open_positions == {}
    # Must not print worse than -hard_loss_limit (float tolerance)
    assert risk.total_pnl >= -risk.hard_loss_limit - 1e-6
    assert risk.worst_pnl_today >= -risk.hard_loss_limit - 1e-6


def test_soft_lock_does_not_force_flatten():
    risk = DailyRiskManager()
    risk.reset_day(date(2025, 6, 2))

    # 5 MES, 21-point adverse ≈ -$525 → soft lock, position remains
    risk.record_fill("MES", 5, 5000.0)
    risk.update_unrealized("MES", 4979.0)

    assert risk.is_locked
    assert "SOFT" in risk.lock_reason
    assert "MES" in risk.open_positions
    assert risk.can_take_new_risk() is False


def test_flatten_all_requires_marks():
    risk = DailyRiskManager()
    risk.reset_day(date(2025, 6, 3))
    risk.record_fill("MES", 1, 5000.0)
    try:
        risk.flatten_all()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "mark price" in str(exc).lower()


if __name__ == "__main__":
    test_hard_limit_caps_adverse_mark()
    test_soft_lock_does_not_force_flatten()
    test_flatten_all_requires_marks()
    print("All risk hard-limit tests passed.")

```

