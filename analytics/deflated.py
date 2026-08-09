"""
Deflated Sharpe Ratio (Bailey & López de Prado, 2014) and
Probability of Backtest Overfitting via CSCV (Bailey et al., 2015).

Mandatory methodology layer for multi-variant research — see research/DESIGN_RULES.md.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import combinations
from math import erfc, exp, log, sqrt
from math import comb as _math_comb
from typing import Dict, Iterable, List, Optional, Tuple

import numpy as np
import pandas as pd

# Euler–Mascheroni constant (Bailey & López de Prado expected-max approximation)
_EMC = 0.5772156649015328606
_MAX_COMBOS_EXACT = 5000


def _norm_cdf(x: float) -> float:
    return 0.5 * erfc(-x / sqrt(2.0))


def _norm_ppf(p: float) -> float:
    """Acklam's rational approximation to the standard normal quantile."""
    if p <= 0.0:
        return -np.inf
    if p >= 1.0:
        return np.inf

    a = (
        -3.969683028665376e01,
        2.209460984245205e02,
        -2.759285104469687e02,
        1.383577518672690e02,
        -3.066479806614736e01,
        2.506628277459239e00,
    )
    b = (
        -5.447609879822406e01,
        1.615858368580409e02,
        -1.556989798598866e02,
        6.680131188771972e01,
        -1.328068155288572e01,
    )
    c = (
        -7.784894002430293e-03,
        -3.223964580411365e-01,
        -2.400758277161838e00,
        -2.549732539343734e00,
        4.374664141464858e00,
        2.938163982698783e00,
    )
    d = (
        7.784695709041462e-03,
        3.224671290700398e-01,
        2.445134137142996e00,
        3.754408661907416e00,
    )

    plow = 0.02425
    phigh = 1.0 - plow

    if p < plow:
        q = sqrt(-2.0 * log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )
    if p > phigh:
        q = sqrt(-2.0 * log(1.0 - p))
        return -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / (
            (((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1.0
        )

    q = p - 0.5
    r = q * q
    return (
        (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5])
        * q
        / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1.0)
    )


def observed_sharpe(returns: pd.Series | np.ndarray, periods_per_year: Optional[float] = None) -> float:
    """Non-annualised Sharpe unless periods_per_year is set."""
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size < 2:
        return 0.0
    mu = float(r.mean())
    sd = float(r.std(ddof=1))
    if sd <= 0.0:
        return 0.0
    sr = mu / sd
    if periods_per_year is not None and periods_per_year > 0:
        sr *= sqrt(periods_per_year)
    return float(sr)


def expected_max_sharpe(n_trials: int, var_sr: float) -> float:
    """
    First-order approximation for E[max SR] under N independent null trials
    (Bailey & López de Prado 2014).
    """
    n = max(int(n_trials), 1)
    if n == 1 or var_sr <= 0.0:
        return 0.0
    z1 = _norm_ppf(1.0 - 1.0 / n)
    z2 = _norm_ppf(1.0 - 1.0 / (n * exp(1.0)))
    return float(sqrt(var_sr) * ((1.0 - _EMC) * z1 + _EMC * z2))


def sharpe_variance(sr: float, n_obs: int, skew: float, kurt: float) -> float:
    """Asymptotic variance of the Sharpe estimator under non-normality."""
    if n_obs < 3:
        return np.inf
    # kurt here is Pearson kurtosis (normal = 3)
    return float((1.0 - skew * sr + ((kurt - 1.0) / 4.0) * sr * sr) / (n_obs - 1))


@dataclass(frozen=True)
class DeflatedSharpeResult:
    sharpe: float
    sr0: float
    dsr: float  # (SR - SR0) / sqrt(Var(SR))  — z-score form
    dsr_prob: float  # Φ(DSR) — Probabilistic Sharpe at the null max
    psr: float  # P(true SR > sr_benchmark)
    n_obs: int
    n_trials: int
    skew: float
    kurtosis: float


def deflated_sharpe(
    returns: pd.Series | np.ndarray,
    n_trials: int,
    sr_benchmark: float = 0.0,
    periods_per_year: Optional[float] = None,
) -> DeflatedSharpeResult:
    """
    Bailey & López de Prado Deflated Sharpe Ratio.

    DSR (z-score) = (SR̂ − SR̂₀) / √Var(SR̂)
    where SR̂₀ is the expected maximum Sharpe under N pure-noise trials.
    Also returns PSR = P(true SR > sr_benchmark) under non-normality.
    """
    r = np.asarray(returns, dtype=float)
    r = r[np.isfinite(r)]
    n_obs = int(r.size)
    n_trials = max(int(n_trials), 1)

    if n_obs < 3:
        return DeflatedSharpeResult(
            sharpe=0.0,
            sr0=0.0,
            dsr=0.0,
            dsr_prob=0.5,
            psr=0.5,
            n_obs=n_obs,
            n_trials=n_trials,
            skew=0.0,
            kurtosis=3.0,
        )

    sr = observed_sharpe(r, periods_per_year=periods_per_year)
    # pandas/numpy: sample skewness; Pearson kurtosis (normal=3)
    s = pd.Series(r)
    skew = float(s.skew()) if n_obs >= 3 else 0.0
    kurt = float(s.kurtosis() + 3.0) if n_obs >= 4 else 3.0  # pandas kurtosis is excess
    if not np.isfinite(skew):
        skew = 0.0
    if not np.isfinite(kurt) or kurt < 1.0:
        kurt = 3.0

    var_sr = sharpe_variance(sr, n_obs, skew, kurt)
    if not np.isfinite(var_sr) or var_sr <= 0.0:
        var_null = 1.0 / (n_obs - 1)
        var_sr = var_null

    # Null variance for expected max (SR ≈ 0 under pure noise)
    var_null = 1.0 / (n_obs - 1)
    sr0 = expected_max_sharpe(n_trials, var_null)

    se = sqrt(var_sr)
    dsr_z = (sr - sr0) / se if se > 0 else 0.0
    dsr_prob = float(_norm_cdf(dsr_z))

    se_bench = se
    psr_z = (sr - sr_benchmark) / se_bench if se_bench > 0 else 0.0
    psr = float(_norm_cdf(psr_z))

    return DeflatedSharpeResult(
        sharpe=float(sr),
        sr0=float(sr0),
        dsr=float(dsr_z),
        dsr_prob=dsr_prob,
        psr=psr,
        n_obs=n_obs,
        n_trials=n_trials,
        skew=skew,
        kurtosis=kurt,
    )


def deflated_profit_factor(profit_factor: Optional[float], dsr_prob: float) -> Optional[float]:
    """
    Lightweight PF haircut: shrink the edge (PF − 1) by the DSR probability.
    Not in the original Bailey papers; reported alongside raw PF for research hygiene.
    """
    if profit_factor is None or not np.isfinite(profit_factor):
        return None
    edge = float(profit_factor) - 1.0
    return float(1.0 + edge * max(0.0, min(1.0, dsr_prob)))


def _block_sharpe(block: np.ndarray) -> float:
    if block.size < 2:
        return 0.0
    sd = float(block.std(ddof=1))
    if sd <= 0.0:
        return 0.0
    return float(block.mean() / sd)


def probability_backtest_overfitting(
    variant_returns: Dict[str, pd.Series],
    n_blocks: int = 16,
    max_combinations: int = _MAX_COMBOS_EXACT,
    random_seed: int = 42,
) -> float:
    """
    Lightweight CSCV estimator of PBO (Bailey et al. 2015).

    Split aligned return series into `n_blocks` sequential blocks. For each
    partition of n_blocks//2 blocks to IS vs OOS, rank variants by IS Sharpe
    and record whether the IS-best underperforms the median OOS Sharpe.

    If C(n_blocks, n_blocks//2) exceeds `max_combinations`, subsample that many
    random combinations (documented default: 5000).
    """
    if not variant_returns:
        return float("nan")

    names = list(variant_returns.keys())
    if len(names) < 2:
        return float("nan")

    # Align on intersection of indices
    frames = []
    for name in names:
        s = variant_returns[name]
        if not isinstance(s, pd.Series):
            s = pd.Series(s)
        frames.append(s.rename(name))
    df = pd.concat(frames, axis=1, join="inner").dropna(how="any")
    if df.shape[0] < n_blocks * 2:
        # Not enough observations for the requested block count
        n_blocks = max(2, (df.shape[0] // 2) * 2)
        n_blocks = min(n_blocks, df.shape[0])
        if n_blocks < 4:
            return float("nan")

    n_blocks = int(n_blocks)
    if n_blocks % 2 == 1:
        n_blocks -= 1
    if n_blocks < 4:
        return float("nan")

    arr = df.to_numpy(dtype=float)  # (T, V)
    t_len = arr.shape[0]
    block_size = t_len // n_blocks
    if block_size < 2:
        return float("nan")

    # Trim to complete blocks
    arr = arr[: block_size * n_blocks]
    blocks = [arr[i * block_size : (i + 1) * block_size] for i in range(n_blocks)]

    half = n_blocks // 2
    all_idx = list(range(n_blocks))
    try:
        n_combo = _math_comb(n_blocks, half)
    except ValueError:
        n_combo = _n_comb(n_blocks, half)

    rng = np.random.default_rng(random_seed)
    if n_combo <= max_combinations:
        partitions: Iterable[Tuple[int, ...]] = combinations(all_idx, half)
    else:
        # Subsample without replacement of unique IS sets
        seen = set()
        sampled: List[Tuple[int, ...]] = []
        # Cap attempts to avoid infinite loop on tiny n_blocks
        attempts = 0
        while len(sampled) < max_combinations and attempts < max_combinations * 20:
            attempts += 1
            pick = tuple(sorted(rng.choice(all_idx, size=half, replace=False).tolist()))
            if pick not in seen:
                seen.add(pick)
                sampled.append(pick)
        partitions = sampled

    overfit = 0
    total = 0
    for is_idx in partitions:
        is_set = set(is_idx)
        oos_idx = [i for i in all_idx if i not in is_set]

        is_concat = np.concatenate([blocks[i] for i in is_idx], axis=0)
        oos_concat = np.concatenate([blocks[i] for i in oos_idx], axis=0)

        is_sr = np.array([_block_sharpe(is_concat[:, v]) for v in range(is_concat.shape[1])])
        oos_sr = np.array([_block_sharpe(oos_concat[:, v]) for v in range(oos_concat.shape[1])])

        best_is = int(np.argmax(is_sr))
        median_oos = float(np.median(oos_sr))
        if oos_sr[best_is] < median_oos:
            overfit += 1
        total += 1

    if total == 0:
        return float("nan")
    return float(overfit / total)


def _n_comb(n: int, k: int) -> int:
    if k < 0 or k > n:
        return 0
    k = min(k, n - k)
    c = 1
    for i in range(k):
        c = c * (n - i) // (i + 1)
    return c


def equity_to_returns(equity: pd.Series) -> pd.Series:
    """Dollar equity → period returns (diff). Suitable for strategy comparison."""
    if equity is None or len(equity) < 2:
        return pd.Series(dtype=float)
    return equity.astype(float).diff().dropna()
