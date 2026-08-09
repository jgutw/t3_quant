# Methodology — Deflated Sharpe & PBO

Status: 2026-08-08 · Mandatory before promoting any signal

---

## 1. Deflated Sharpe Ratio (Bailey & López de Prado, 2014)

**Formula**

$$\widehat{DSR} = \frac{\widehat{SR} - \widehat{SR}_0}{\sqrt{\widehat{\mathrm{Var}}(\widehat{SR})}}$$

where \(\widehat{SR}_0\) is the expected maximum Sharpe under the null that all \(N\) trials are pure noise (non-normality corrected via sample skewness/kurtosis).

**Rule**

Every multi-variant experiment must:

- record the number of trials \(N\)
- report **both** raw PF/Sharpe **and** the deflated version

Raw PF / Sharpe alone is not evidence.

---

## 2. Probability of Backtest Overfitting — CSCV (Bailey et al., 2015)

**Definition**

PBO = probability that the in-sample best configuration underperforms the median out-of-sample configuration, estimated via Combinatorially Symmetric Cross-Validation (CSCV) on saved variant return series.

**Rule**

Require **low PBO** before any variant is promoted. Classic hold-out does not control for multiple testing.

---

## 3. Implementation

Code lives in `analytics/deflated.py` (wired through `analytics/metrics.py`); covered by `tests/test_deflated_metrics.py`.
