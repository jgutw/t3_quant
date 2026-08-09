"""Tests for Deflated Sharpe and CSCV PBO (pure-noise null behaviour)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from analytics.deflated import deflated_sharpe, probability_backtest_overfitting


def test_dsr_falls_when_n_trials_increases_on_noise():
    rng = np.random.default_rng(0)
    # Pure noise; fixed path so only N changes the haircut
    returns = pd.Series(rng.normal(0.0, 1.0, size=500))

    dsr_small = deflated_sharpe(returns, n_trials=2)
    dsr_large = deflated_sharpe(returns, n_trials=200)

    assert dsr_large.sr0 > dsr_small.sr0
    assert dsr_large.dsr < dsr_small.dsr
    assert dsr_large.dsr_prob <= dsr_small.dsr_prob + 1e-12


def test_pbo_near_half_on_pure_noise_variants():
    rng = np.random.default_rng(1)
    n = 640  # divisible by n_blocks=16
    variants = {
        f"v{i}": pd.Series(rng.normal(0.0, 1.0, size=n))
        for i in range(8)
    }
    pbo = probability_backtest_overfitting(variants, n_blocks=16, max_combinations=2000, random_seed=7)
    assert np.isfinite(pbo)
    # Under pure noise, PBO should concentrate near 0.5
    assert 0.30 <= pbo <= 0.70


def test_dsr_result_fields_finite():
    rng = np.random.default_rng(2)
    returns = pd.Series(rng.normal(0.05, 1.0, size=300))  # mild positive drift
    res = deflated_sharpe(returns, n_trials=10, sr_benchmark=0.0)
    assert res.n_obs == 300
    assert np.isfinite(res.sharpe)
    assert np.isfinite(res.dsr)
    assert 0.0 <= res.dsr_prob <= 1.0
    assert 0.0 <= res.psr <= 1.0
