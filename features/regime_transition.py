"""
Lightweight online regime-transition detector (CUSUM-style z-break).

Fixed v1 parameters for regime_transition_v1 — no grids.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class RegimeTransitionParams:
    L: int = 12  # bars in short sum (~1 hour on 5m)
    W: int = 78  # lookback for mean/std of s (~1 RTH day)
    theta: float = 2.0  # |z| fire threshold
    H: int = 6  # transition window length (bars)
    C: int = 6  # cooldown bars after window ends


def compute_transition_z(
    close: pd.Series,
    params: RegimeTransitionParams | None = None,
) -> pd.DataFrame:
    """
    Compute z_t and fire events.

    r_t = log return
    s_t = rolling sum of r over L bars
    z_t = (s_t - μ_W) / σ_W

    Fire: first bar where |z| >= theta after having been < theta,
    subject to transition window + cooldown.
    """
    p = params or RegimeTransitionParams()
    close = close.astype(float)
    r = np.log(close / close.shift(1))
    s = r.rolling(p.L, min_periods=p.L).sum()
    mu = s.rolling(p.W, min_periods=p.W).mean()
    sigma = s.rolling(p.W, min_periods=p.W).std()
    z = (s - mu) / sigma

    abs_z = z.abs()
    previously_below = abs_z.shift(1).lt(p.theta).fillna(True)
    raw_cross = abs_z.ge(p.theta) & previously_below & z.notna() & sigma.gt(0)

    n = len(close)
    fire = np.zeros(n, dtype=bool)
    fire_sign = np.zeros(n, dtype=float)
    in_transition = np.zeros(n, dtype=bool)

    z_arr = z.to_numpy(dtype=float)
    cross_arr = raw_cross.to_numpy(dtype=bool)

    i = 0
    while i < n:
        if not cross_arr[i] or not np.isfinite(z_arr[i]) or z_arr[i] == 0.0:
            i += 1
            continue

        # Open transition window [i, i+H)
        sign = 1.0 if z_arr[i] > 0 else -1.0
        fire[i] = True
        fire_sign[i] = sign
        win_end = min(i + p.H, n)
        in_transition[i:win_end] = True

        # Cooldown after window: no new fire for C bars
        i = win_end + p.C

    return pd.DataFrame(
        {
            "z": z,
            "s": s,
            "fire": fire,
            "fire_sign": fire_sign,
            "in_transition": in_transition,
        },
        index=close.index,
    )
