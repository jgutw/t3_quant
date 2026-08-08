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
