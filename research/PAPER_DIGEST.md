# t3_quant Paper Digest
Status: 2026-08-08  
Categories completed: 1 (Mean-Reversion) + 2 (Trend Failure / Overfitting)

---

## CATEGORY 1 — Mean-Reversion / Overnight-Intraday

### Paper 1
**Optimal Mean Reversion Trading with Transaction Costs and Stop-Loss Exit**  
Leung & Li (2015)

Core mathematical result: under OU dynamics with transaction costs and a hard stop-loss L, the optimal entry region is a bounded interval (a*, b*) that lies strictly above L. Raising L forces the optimal take-profit downward. Fixed costs make the admissible entry band narrower.

Implication for us: any mean-reversion sleeve must enforce L < entry zone. Stop and target are coupled parameters, not independent.

Status: Design rule (permanent)

---

### Paper 2
**Structural Limits of OHLCV-Based Intraday Signals in MNQ Futures**  
Mesfin (2026)

Empirical ceiling: on 5-min MNQ the maximum achievable gross edge across 14 signal families is ~0.07–1.50 points while realistic round-trip friction is 2.0 points. Nothing cleared a rigorous walk-forward + cost + year-stability test.

Implication for us: adopt the same evaluation bar (OOS T≥2, ≥30 trades, positive after costs, consistent across years). Gross edge must exceed our round-trip cost before further development.

Status: Evaluation standard (permanent)

---

### Paper 3
**Market Making in Spot Precious Metals**  
Barzykin, Bergault & Guéant (2024/2026)

EFP (futures–spot) in metals is co-integrated with multiple relaxation speeds and is best modelled as a nested OU. Futures are the dominant liquidity venue.

Implication for us: future MGC/SIL work should use multi-factor mean-reversion, not single-speed OU.

Status: Parked — metals sleeve

---

### Paper 4
**Optimal Multiple Trading Times Under the Exponential OU Model**  
Leung, Li & Wang (2015/2018)

Under exponential OU with fixed transaction costs the optimal entry region is disconnected: (0, A) ∪ (B, ∞). The investor waits both when price is too high and when it is too close to zero.

Implication for us: fixed costs create a lower “do-not-enter” zone. Reinforces the band-entry rule from Paper 1.

Status: Design rule (permanent)

---

### Paper 5
**The Price Impact of Order Book Events**  
Cont, Kukanov & Stoikov (2011)

Short-term mid-price changes are linear in Order Flow Imbalance / depth. Trade volume is a weaker and noisier predictor.

Implication for us: volume-spike signals are structurally weak. Parked until we move to live order-book data.

Status: Parked — microstructure

---

### Paper 6
**Overnight-Intraday Reversal Everywhere**  
Della Corte et al. (2022)

Buying low overnight returns and selling high overnight returns produces 2–5× stronger intraday excess returns than conventional close-to-close reversal across equity-index, rates, commodity and currency futures. Driven by market-maker liquidity provision at the open.

Implication for us: highest-conviction single-asset candidate on MES is an overnight → intraday fade that respects the entry-band and stop-coupling rules.

Status: Candidate — primary active direction on MES

---

## CATEGORY 2 — Why Trend Failed / Overfitting Control

### Paper 7
**Is Trend Still Your Friend?**  
Kurth, Eisler, Rej, Bouchaud (2026)

Central result: post-2008 short-horizon trend Sharpe collapsed on small-tick futures (equity indices including ES/MES) while remaining intact on large-tick futures (most commodities). The cause is microstructural: HFT market-makers withdraw liquidity in front of predictable directional flow on sparse (small-tick) books, breaking the self-fulfilling impact loop that trend depends on. Capacity, electronification and simple order-flow stories are rejected on timing and magnitude grounds. Zero-lag execution still shows flat PnL → the signal itself degraded.

Implication for us:
- MES short-horizon trend family is structurally closed.
- Same trend architectures remain worth testing later on MGC/SIL (large-tick regime).
- Further MES trend filter engineering has low expected value.

Status: Core explanatory result (permanent)

---

### Paper 8
**The Deflated Sharpe Ratio**  
Bailey & López de Prado (2014)

Raw Sharpe/PF is inflated by (a) the number of trials N and (b) non-normality. The Deflated Sharpe Ratio subtracts the expected maximum Sharpe under the null of pure noise given N trials and accounts for skewness/kurtosis.

Implication for us: every multi-variant experiment must record N and report both raw and deflated metrics. Mandatory before any variant is promoted.

Status: Methodology requirement (permanent)

---

### Paper 9
**The Probability of Backtest Overfitting**  
Bailey, Borwein, López de Prado & Zhu (2015)

Defines PBO via Combinatorially Symmetric Cross-Validation (CSCV): probability that the in-sample best configuration underperforms the median out-of-sample. Classic hold-out does not control multiple testing.

Implication for us: implement a lightweight CSCV/PBO estimator on saved variant equity curves before promoting any signal.

Status: Methodology requirement (permanent)

---

## CURRENT RESEARCH POSTURE

| Direction                        | Status                          |
|----------------------------------|---------------------------------|
| MES short-horizon trend          | Closed                          |
| MES mean-reversion / overnight-intraday | Active primary             |
| Same trend code on MGC/SIL       | Deferred (tick-size test)       |
| Deflated Sharpe + PBO in metrics | Required infrastructure         |

---

## CATEGORY 3 — Regime Detection / Adaptive Trend-vs-Chop

### Paper 10
**Usage of the Hurst Exponent for Short Term Trading Strategies**  
Marton & Cakir (2022)

Hurst H used strictly as regime gate (H>0.5 trend, H<0.5 mean-reversion). SuperTrend supplies direction once regime is declared. Kalman filter preferred to FFT for noise reduction but still lags and can mis-label strong trends. Window-length dependent. Tested on SPY/QQQ, not futures microstructure.

Implication: architectural pattern (regime gate → existing directional indicator). Still a trend strategy on small-tick if applied to MES. Useful diagnostic: compute rolling Hurst on MES vs MGC/SIL. Not primary MES edge.

Status: Low priority on MES; diagnostic on metals.

---

### Paper 11
**Slow Momentum with Fast Reversion**  
Wood, Roberts & Zohren (Oxford-Man, 2022)

Online Gaussian-Process changepoint detection produces severity ν_t and location γ_t. These are fed to an LSTM that learns to balance slow momentum (persistent trends) against fast mean-reversion (quick flip after detected turning points). Sharpe improvement ~33% overall, ~66% in 2015–2020 on 50 liquid futures. Directly addresses the failure mode of lagging trend signals at turning points.

Implication: highest-conviction regime architecture. Unifies trend and mean-reversion instead of treating them as separate sleeves. Full GP-LSTM too heavy for our account; the core idea (lightweight changepoint gate → short reversion overlay or flat, otherwise slow directional) is the correct next experiment template.

Status: Highest-priority regime idea.

---

### Paper 12
**Multi-Scale Markov-Switching GARCH**  
Chaudhary (2026)

Triple-timeframe (1D/4H/1H) MS-GARCH with Calm/Turbulent/Crisis states, joint 27-dim probability tensor, Shannon-entropy filter. Strong volatility-forecast results on EUR/USD; directional IC small. Author positions as risk tool, not alpha engine.

Implication: multi-scale volatility states and entropy filter are useful risk-layer primitives. Full model far too heavy. Extract only a simple low-dimensional vol-regime label or entropy gate if needed.

Status: Risk-layer pattern only. Reject full implementation.

---

### Paper 13
**Structural Clustering of Volatility Regimes**  
Prakash et al. (2021)

Non-parametric: Mood change-point → Wasserstein distance matrix → self-tuning spectral clustering discovers number of vol regimes. Online nearest-regime match used for risk avoidance.

Implication: clean way to learn regime count without pre-specifying k. Best use is risk avoidance / size scaling, not directional alpha.

Status: Optional risk-layer pattern.

---

### CATEGORY 3 SYNTHESIS (permanent)

| Mechanism | MES directional potential | Best use | Priority |
|-----------|---------------------------|----------|----------|
| Hurst + SuperTrend | Low | Diagnostic MES vs metals | Low |
| Online changepoint → slow trend + fast reversion | Highest in category | Next directional experiment template | Highest |
| Full MS-GARCH / 27-expert | Very low | Do not implement | Reject |
| Wasserstein/spectral vol clustering | Low as alpha | Optional risk gate | Medium (risk) |
| Simple realised-vol / entropy filter | Indirect | Cheap risk / “trade only when calm” | Medium |

MES pure trend and static overnight fade remain closed. Next directional work on MES must be regime-transition gated.
