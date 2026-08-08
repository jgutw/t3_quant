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
