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
