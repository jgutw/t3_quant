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
