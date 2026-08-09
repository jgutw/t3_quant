"""
Event-driven backtest engine V2
Hard guarantee: risk manager sees adverse prices before any decision.
A stop or risk lock is always executed at the stop price, not the close.
"""

from __future__ import annotations

from datetime import time as dt_time
from typing import Dict, Optional, Tuple

import numpy as np
import pandas as pd
from dataclasses import dataclass, field

from config.settings import ACCOUNT, CONTRACTS
from risk.daily_risk_manager import DailyRiskManager
from strategies.base import StrategyBase


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
    worst_intraday: float = 0.0  # most negative *daily* risk equity seen
    worst_intraday_pnl: float = 0.0
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
      - Equity curve is lifetime cumulative (risk.total_pnl is daily-only).

    Optional bracket mode (overnight fade etc.):
      - Per-bar stop/target distances from the strategy
      - Hold until stop / target / session_flatten_time (ignore signal flat)
      - No re-entry after an exit until the next session_start
      - Entry fill at bar open + adverse slip when entry_on_open=True
    """

    def __init__(
        self,
        strategy: StrategyBase,
        risk_manager: DailyRiskManager,
        symbol: str = "MES",
        stop_points: float = 8.0,
        commission_per_side: float = ACCOUNT.commission_per_contract,
        slippage_ticks: float = 1.0,
        bracket_hold: bool = False,
        session_flatten_time: Optional[dt_time] = None,
        entry_on_open: bool = False,
        max_hold_bars: Optional[int] = None,
        allow_intrasession_reentry: bool = False,
    ):
        self.strategy = strategy
        self.risk = risk_manager
        self.symbol = symbol
        self.stop_points = stop_points
        self.commission = commission_per_side
        self.slippage_ticks = slippage_ticks
        self.spec = CONTRACTS[symbol]
        self.bracket_hold = bracket_hold
        self.session_flatten_time = session_flatten_time
        self.entry_on_open = entry_on_open
        self.max_hold_bars = max_hold_bars
        self.allow_intrasession_reentry = allow_intrasession_reentry

    def run(
        self,
        data: pd.DataFrame,
        higher_tf: Optional[Dict[str, pd.Series]] = None,
        cpr: Optional[dict] = None,
        orb: Optional[tuple] = None,
    ) -> BacktestResult:
        signals = self.strategy.generate_signals(
            data,
            higher_tf_closes=higher_tf,
            cpr_levels=cpr,
            orb_high=orb[0] if orb else None,
            orb_low=orb[1] if orb else None,
        )

        stop_series = getattr(self.strategy, "stop_points_by_bar", None)
        target_series = getattr(self.strategy, "target_points_by_bar", None)

        equity: list[float] = []
        trades: list = []
        locked_days: set = set()
        worst_daily = 0.0  # min risk.worst_pnl_today (hard-limit check)
        cum_realized = 0.0  # lifetime closed-trade PnL

        position = 0
        entry_price = 0.0
        entry_time = None
        entry_bar_i: Optional[int] = None
        active_stop = float(self.stop_points)
        active_target: Optional[float] = None
        prev_ts = None
        prev_close = None
        block_reentry_until_session = False

        n = len(data)
        opens = data["open"].to_numpy(dtype=float)
        highs = data["high"].to_numpy(dtype=float)
        lows = data["low"].to_numpy(dtype=float)
        closes = data["close"].to_numpy(dtype=float)
        session_starts = data["session_start"].to_numpy(dtype=bool)
        sig = signals.to_numpy(dtype=float)
        index = data.index
        stop_arr = stop_series.to_numpy(dtype=float) if stop_series is not None else None
        target_arr = (
            target_series.to_numpy(dtype=float) if target_series is not None else None
        )

        for i in range(n):
            ts = index[i]
            o, h, l, c = opens[i], highs[i], lows[i], closes[i]
            if bool(session_starts[i]):
                block_reentry_until_session = False

            # --- 0. RTH-flat before day rollover ---
            if (
                prev_ts is not None
                and ts.date() != prev_ts.date()
                and position != 0
                and prev_close is not None
            ):
                reason = "session_end" if self.bracket_hold else "session_eod"
                cum_realized += self._close(
                    position, entry_price, prev_close, entry_time, prev_ts, trades, reason
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
                if self.bracket_hold and not self.allow_intrasession_reentry:
                    block_reentry_until_session = True
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)

            # --- 1. Day reset ---
            self.risk.reset_day(ts.date())

            # --- 2/3. Flat: entry ---
            if position == 0:
                if not self.risk.can_take_new_risk():
                    locked_days.add(ts.date())
                    equity.append(cum_realized)
                    worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                    prev_ts, prev_close = ts, c
                    continue

                target = int(sig[i])
                can_enter = (
                    target != 0
                    and self.risk.can_take_new_risk()
                    and not (self.bracket_hold and block_reentry_until_session)
                )
                if can_enter:
                    stop_pts = self._lookup_arr(stop_arr, i, self.stop_points)
                    size = self.strategy.size_position(self.symbol, int(target), stop_pts)
                    if size != 0:
                        position = size
                        entry_price = self._slipped_ohlc(o, h, l, c, size, is_entry=True)
                        entry_time = ts
                        entry_bar_i = i
                        active_stop = stop_pts
                        active_target = (
                            self._lookup_arr(target_arr, i, stop_pts)
                            if self.bracket_hold and target_arr is not None
                            else None
                        )
                        self.risk.record_fill(self.symbol, size, entry_price)

                        if self.bracket_hold:
                            closed, cum_realized = self._manage_open_ohlc(
                                ts, o, h, l, c, position, entry_price, entry_time,
                                active_stop, active_target, trades, locked_days,
                                cum_realized,
                            )
                            if closed:
                                position = 0
                                entry_time = None
                                entry_bar_i = None
                                active_target = None
                                if self.bracket_hold and not self.allow_intrasession_reentry:
                                    block_reentry_until_session = True

                mark = l if position > 0 else (h if position < 0 else c)
                eq = cum_realized + self._open_unrealized(position, entry_price, mark)
                equity.append(eq)
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, c
                continue

            # --- Open position: adverse → risk → stop → target → time → signals ---
            if position > 0:
                adverse_price = l
                stop_price = entry_price - active_stop
                stop_hit = adverse_price <= stop_price
                target_price = (
                    entry_price + active_target if active_target is not None else None
                )
                target_hit = target_price is not None and h >= target_price
            else:
                adverse_price = h
                stop_price = entry_price + active_stop
                stop_hit = adverse_price >= stop_price
                target_price = (
                    entry_price - active_target if active_target is not None else None
                )
                target_hit = target_price is not None and l <= target_price

            was_open = self.symbol in self.risk.open_positions
            self.risk.update_unrealized(self.symbol, adverse_price)
            worst_daily = min(worst_daily, self.risk.worst_pnl_today)

            if was_open and self.symbol not in self.risk.open_positions:
                locked_days.add(ts.date())
                exit_px = stop_price if stop_hit else adverse_price
                reason = "risk_flatten" if self.bracket_hold else "hard_limit"
                cum_realized += self._record_external_flatten(
                    position, entry_price, exit_px, entry_time, ts, trades, reason
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
                if self.bracket_hold and not self.allow_intrasession_reentry:
                    block_reentry_until_session = True
                equity.append(cum_realized)
                prev_ts, prev_close = ts, c
                continue

            if not self.risk.can_take_new_risk():
                locked_days.add(ts.date())
                reason = "risk_flatten" if self.bracket_hold else "risk_lock"
                cum_realized += self._close(
                    position, entry_price, stop_price, entry_time, ts, trades, reason
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
                if self.bracket_hold and not self.allow_intrasession_reentry:
                    block_reentry_until_session = True
                equity.append(cum_realized)
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, c
                continue

            if stop_hit:
                cum_realized += self._close(
                    position, entry_price, stop_price, entry_time, ts, trades, "stop"
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
                if self.bracket_hold and not self.allow_intrasession_reentry:
                    block_reentry_until_session = True
                equity.append(cum_realized)
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, c
                continue

            if target_hit and target_price is not None:
                cum_realized += self._close(
                    position, entry_price, float(target_price), entry_time, ts, trades, "target"
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
                if self.bracket_hold and not self.allow_intrasession_reentry:
                    block_reentry_until_session = True
                equity.append(cum_realized)
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, c
                continue

            # Max hold (count includes entry bar as bar 1)
            if (
                self.max_hold_bars is not None
                and entry_bar_i is not None
                and (i - entry_bar_i + 1) >= int(self.max_hold_bars)
            ):
                exit_px = self._slipped_ohlc(o, h, l, c, position, is_entry=False)
                cum_realized += self._close(
                    position, entry_price, exit_px, entry_time, ts, trades, "max_hold"
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
                if self.bracket_hold and not self.allow_intrasession_reentry:
                    block_reentry_until_session = True
                equity.append(cum_realized)
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, c
                continue

            if (
                self.session_flatten_time is not None
                and self._bar_time(ts) >= self.session_flatten_time
            ):
                exit_px = self._slipped_ohlc(o, h, l, c, position, is_entry=False)
                cum_realized += self._close(
                    position, entry_price, exit_px, entry_time, ts, trades, "session_end"
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
                if self.bracket_hold and not self.allow_intrasession_reentry:
                    block_reentry_until_session = True
                equity.append(cum_realized)
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, c
                continue

            if not self.risk.can_take_new_risk():
                locked_days.add(ts.date())
                equity.append(
                    cum_realized + self._open_unrealized(position, entry_price, adverse_price)
                )
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, c
                continue

            if self.bracket_hold:
                equity.append(
                    cum_realized + self._open_unrealized(position, entry_price, adverse_price)
                )
                worst_daily = min(worst_daily, self.risk.worst_pnl_today)
                prev_ts, prev_close = ts, c
                continue

            target = sig[i]
            if target == 0:
                exit_px = self._slipped_ohlc(o, h, l, c, position, is_entry=False)
                cum_realized += self._close(
                    position, entry_price, exit_px, entry_time, ts, trades, "signal"
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
            elif np.sign(target) != np.sign(position):
                exit_px = self._slipped_ohlc(o, h, l, c, position, is_entry=False)
                cum_realized += self._close(
                    position, entry_price, exit_px, entry_time, ts, trades, "reverse"
                )
                position = 0
                entry_time = None
                entry_bar_i = None
                active_target = None
                if self.risk.can_take_new_risk():
                    stop_pts = self._lookup_arr(stop_arr, i, self.stop_points)
                    size = self.strategy.size_position(self.symbol, int(target), stop_pts)
                    if size != 0:
                        position = size
                        entry_price = self._slipped_ohlc(o, h, l, c, size, is_entry=True)
                        entry_time = ts
                        entry_bar_i = i
                        active_stop = stop_pts
                        self.risk.record_fill(self.symbol, size, entry_price)

            mark = adverse_price if position != 0 else c
            equity.append(
                cum_realized + self._open_unrealized(position, entry_price, mark)
            )
            worst_daily = min(worst_daily, self.risk.worst_pnl_today)
            prev_ts, prev_close = ts, c

        if position != 0:
            reason = "session_end" if self.bracket_hold else "eod"
            cum_realized += self._close(
                position,
                entry_price,
                float(data["close"].iloc[-1]),
                entry_time,
                data.index[-1],
                trades,
                reason,
            )
            worst_daily = min(worst_daily, self.risk.worst_pnl_today)
            if equity:
                equity[-1] = cum_realized
            else:
                equity.append(cum_realized)

        eq = pd.Series(equity, index=data.index[: len(equity)])
        max_dd = (eq - eq.cummax()).min() if len(eq) else 0.0
        total_comm = sum(abs(t.qty) * self.commission * 2 for t in trades)

        return BacktestResult(
            trades=trades,
            equity_curve=eq,
            final_pnl=float(cum_realized),
            max_dd=float(max_dd),
            num_trades=len(trades),
            locked_out_days=len(locked_days),
            worst_intraday=float(worst_daily),
            worst_intraday_pnl=float(worst_daily),
            total_commission=float(total_comm),
        )

    # ------------------------------------------------------------------
    def _manage_open_ohlc(
        self,
        ts: pd.Timestamp,
        o: float,
        h: float,
        l: float,
        c: float,
        position: int,
        entry_price: float,
        entry_time: pd.Timestamp,
        active_stop: float,
        active_target: Optional[float],
        trades: list,
        locked_days: set,
        cum_realized: float,
    ) -> Tuple[bool, float]:
        """Same-bar manage after entry. Returns (closed, cum_realized)."""
        if position > 0:
            adverse_price = l
            stop_price = entry_price - active_stop
            stop_hit = adverse_price <= stop_price
            target_price = (
                entry_price + active_target if active_target is not None else None
            )
            target_hit = target_price is not None and h >= target_price
        else:
            adverse_price = h
            stop_price = entry_price + active_stop
            stop_hit = adverse_price >= stop_price
            target_price = (
                entry_price - active_target if active_target is not None else None
            )
            target_hit = target_price is not None and l <= target_price

        was_open = self.symbol in self.risk.open_positions
        self.risk.update_unrealized(self.symbol, adverse_price)

        if was_open and self.symbol not in self.risk.open_positions:
            locked_days.add(ts.date())
            exit_px = stop_price if stop_hit else adverse_price
            reason = "risk_flatten" if self.bracket_hold else "hard_limit"
            cum_realized += self._record_external_flatten(
                position, entry_price, exit_px, entry_time, ts, trades, reason
            )
            return True, cum_realized

        if not self.risk.can_take_new_risk():
            locked_days.add(ts.date())
            reason = "risk_flatten" if self.bracket_hold else "risk_lock"
            cum_realized += self._close(
                position, entry_price, stop_price, entry_time, ts, trades, reason
            )
            return True, cum_realized

        if stop_hit:
            cum_realized += self._close(
                position, entry_price, stop_price, entry_time, ts, trades, "stop"
            )
            return True, cum_realized

        if target_hit and target_price is not None:
            cum_realized += self._close(
                position, entry_price, float(target_price), entry_time, ts, trades, "target"
            )
            return True, cum_realized

        if (
            self.session_flatten_time is not None
            and self._bar_time(ts) >= self.session_flatten_time
        ):
            exit_px = self._slipped_ohlc(o, h, l, c, position, is_entry=False)
            cum_realized += self._close(
                position, entry_price, exit_px, entry_time, ts, trades, "session_end"
            )
            return True, cum_realized

        return False, cum_realized

    def _open_unrealized(self, qty: int, entry: float, mark: float) -> float:
        if qty == 0:
            return 0.0
        points = (mark - entry) * np.sign(qty)
        return float(points * abs(qty) * self.spec.multiplier)

    @staticmethod
    def _lookup_arr(arr: Optional[np.ndarray], i: int, default: float) -> float:
        if arr is None or i >= len(arr):
            return float(default)
        val = float(arr[i])
        if not np.isfinite(val):
            return float(default)
        return val

    @staticmethod
    def _bar_time(ts: pd.Timestamp) -> dt_time:
        if getattr(ts, "tzinfo", None) is not None:
            ts = ts.tz_convert("America/New_York")
        return dt_time(ts.hour, ts.minute, ts.second)

    def _slipped_ohlc(
        self, o: float, h: float, l: float, c: float, qty: int, is_entry: bool
    ) -> float:
        if self.entry_on_open and is_entry:
            base = float(o)
        else:
            base = (float(o) + float(h) + float(l) + float(c)) / 4.0
        slip = self.slippage_ticks * self.spec.tick_size
        direction = 1 if qty > 0 else -1
        if is_entry:
            return base + direction * slip
        return base - direction * slip

    def _slipped(
        self, ts: pd.Timestamp, bar: pd.Series, qty: int, is_entry: bool
    ) -> float:
        return self._slipped_ohlc(
            float(bar["open"]),
            float(bar["high"]),
            float(bar["low"]),
            float(bar["close"]),
            qty,
            is_entry,
        )

    def _record_external_flatten(
        self,
        qty: int,
        entry: float,
        exit_raw: float,
        entry_time: pd.Timestamp,
        ts: pd.Timestamp,
        trades: list,
        reason: str,
    ) -> float:
        points = (float(exit_raw) - entry) * np.sign(qty)
        gross = points * abs(qty) * self.spec.multiplier
        costs = abs(qty) * self.commission * 2
        pnl = gross - costs
        trades.append(
            Trade(
                symbol=self.symbol,
                entry_time=entry_time,
                exit_time=ts,
                qty=qty,
                entry_price=entry,
                exit_price=float(exit_raw),
                pnl=pnl,
                reason=reason,
            )
        )
        return pnl

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
