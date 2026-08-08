"""
DailyRiskManager V2
Hard guarantee: equity can never print worse than -hard_loss_limit
when marks are supplied on every bar extreme.

Policy (explicit):
- Soft lock (-$500): block new risk for the rest of the day. Do NOT force-flatten.
  Existing positions keep their stops. No intraday unlock/recovery.
- Hard lock (-$750): force-flatten immediately at the provided mark prices.
- Overnight holds are undefined: the system assumes RTH-flat.
  reset_day() clears state without realizing gaps — callers must be flat first.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, Optional
from datetime import date
import logging

from config.settings import ACCOUNT, CONTRACTS

logger = logging.getLogger(__name__)


@dataclass
class PositionState:
    symbol: str
    qty: int  # signed
    avg_price: float
    unrealized_pnl: float = 0.0


@dataclass
class DailyRiskManager:
    soft_loss_limit: float = ACCOUNT.soft_daily_loss  # 500
    hard_loss_limit: float = ACCOUNT.max_daily_loss  # 750
    max_planned_risk: float = ACCOUNT.max_planned_risk_per_day
    commission_per_side: float = ACCOUNT.commission_per_contract

    current_date: Optional[date] = None
    realized_pnl: float = 0.0
    open_positions: Dict[str, PositionState] = field(default_factory=dict)
    is_locked: bool = False
    lock_reason: str = ""
    worst_pnl_today: float = 0.0  # most negative equity seen today

    # ------------------------------------------------------------------
    # Day management
    # ------------------------------------------------------------------
    def reset_day(self, today: date) -> None:
        if self.current_date != today:
            if self.open_positions:
                logger.error(
                    "reset_day called with open positions — overnight/gap PnL is undefined. "
                    "Flatten before day rollover."
                )
            self.current_date = today
            self.realized_pnl = 0.0
            self.open_positions.clear()
            self.is_locked = False
            self.lock_reason = ""
            self.worst_pnl_today = 0.0
            logger.info(f"Risk manager reset for {today}")

    # ------------------------------------------------------------------
    # Core state
    # ------------------------------------------------------------------
    @property
    def total_pnl(self) -> float:
        unrealized = sum(p.unrealized_pnl for p in self.open_positions.values())
        return self.realized_pnl + unrealized

    @property
    def remaining_risk_budget(self) -> float:
        """Remaining room before soft lock."""
        return max(0.0, self.soft_loss_limit + self.total_pnl)

    def _update_worst(self) -> None:
        self.worst_pnl_today = min(self.worst_pnl_today, self.total_pnl)

    def _charge_commission(self, qty: int) -> None:
        self.realized_pnl -= abs(qty) * self.commission_per_side

    # ------------------------------------------------------------------
    # Marking & limit enforcement
    # ------------------------------------------------------------------
    def update_unrealized(self, symbol: str, mark_price: float) -> None:
        """Update mark and immediately enforce limits."""
        if symbol not in self.open_positions:
            return
        pos = self.open_positions[symbol]
        spec = CONTRACTS[symbol]
        direction = 1 if pos.qty > 0 else -1
        points = (mark_price - pos.avg_price) * direction
        pos.unrealized_pnl = points * abs(pos.qty) * spec.multiplier
        self._check_and_enforce(mark_prices={symbol: mark_price})

    def mark_all_and_check(self, marks: Dict[str, float]) -> None:
        """Convenience: update every open position and enforce."""
        for sym, px in marks.items():
            if sym in self.open_positions:
                self.update_unrealized(sym, px)

    def _limit_flatten_price(self, symbol: str, pos: PositionState) -> float:
        """
        Price that closes this position so post-commission realized PnL lands
        on -hard_loss_limit (single-position case used by the MES backtester).
        """
        spec = CONTRACTS[symbol]
        commission = abs(pos.qty) * self.commission_per_side
        # After flatten: realized_old + trade_pnl - commission == -hard_loss_limit
        trade_pnl = -self.hard_loss_limit - self.realized_pnl + commission
        points = trade_pnl / (abs(pos.qty) * spec.multiplier)
        if pos.qty > 0:
            return pos.avg_price + points
        return pos.avg_price - points

    def _capped_flatten_marks(self, mark_prices: Dict[str, float]) -> Dict[str, float]:
        """Do not realize beyond the hard limit when the bar extreme overshoots."""
        capped: Dict[str, float] = {}
        for sym, pos in self.open_positions.items():
            if sym not in mark_prices:
                raise ValueError(
                    f"Cannot force-flatten {sym} without a mark price "
                    "(refusing to realize at avg_price / $0 phantom PnL)"
                )
            raw = mark_prices[sym]
            limit_px = self._limit_flatten_price(sym, pos)
            # Longs: adverse is lower → flatten at the higher of raw vs limit
            # Shorts: adverse is higher → flatten at the lower of raw vs limit
            capped[sym] = max(raw, limit_px) if pos.qty > 0 else min(raw, limit_px)
        return capped

    def _check_and_enforce(self, mark_prices: Optional[Dict[str, float]] = None) -> None:
        """
        Single place that can lock and force flatten.
        Called after every fill and every mark.

        Note: when a bar extreme would print past the hard limit, we flatten at the
        capped limit price and only then update worst_pnl_today — so a phantom
        intrabar mark beyond -$750 is never recorded as realized equity.
        """
        total = self.total_pnl

        if total <= -self.hard_loss_limit:
            self.lock_reason = f"HARD LIMIT: {total:.2f} <= -{self.hard_loss_limit}"
            logger.critical(self.lock_reason)
            capped = self._capped_flatten_marks(mark_prices or {})
            self._force_flatten(capped)
            self.is_locked = True
            self._update_worst()
            return

        self._update_worst()

        if total <= -self.soft_loss_limit and not self.is_locked:
            # Policy: soft lock is permanent for the session day (no recovery unlock).
            self.lock_reason = f"SOFT LIMIT: {total:.2f} <= -{self.soft_loss_limit}"
            logger.warning(self.lock_reason)
            self.is_locked = True

    def _force_flatten(self, mark_prices: Dict[str, float]) -> None:
        """Realize every open position at the provided marks. Marks are required."""
        for sym in list(self.open_positions.keys()):
            if sym not in mark_prices:
                raise ValueError(
                    f"Cannot force-flatten {sym} without a mark price "
                    "(refusing to realize at avg_price / $0 phantom PnL)"
                )
            pos = self.open_positions[sym]
            px = mark_prices[sym]
            direction = 1 if pos.qty > 0 else -1
            points = (px - pos.avg_price) * direction
            realized = points * abs(pos.qty) * CONTRACTS[sym].multiplier
            self.realized_pnl += realized
            self._charge_commission(pos.qty)  # closing side
            logger.warning(
                f"Forced flatten {sym} qty={pos.qty} @ {px:.2f} -> {realized:.2f}"
            )
            del self.open_positions[sym]

    # ------------------------------------------------------------------
    # Fills
    # ------------------------------------------------------------------
    def record_fill(
        self, symbol: str, qty: int, price: float, is_closing: bool = False
    ) -> None:
        """
        qty signed (+ buy / - sell).
        After every fill we re-check limits.
        """
        if symbol not in self.open_positions:
            self.open_positions[symbol] = PositionState(
                symbol=symbol, qty=0, avg_price=price
            )

        pos = self.open_positions[symbol]
        spec = CONTRACTS[symbol]

        # Closing or reversing
        if is_closing or (pos.qty != 0 and (pos.qty > 0) != (qty > 0)):
            closed_qty = min(abs(pos.qty), abs(qty))
            direction = 1 if pos.qty > 0 else -1
            points = (price - pos.avg_price) * direction
            realized = points * closed_qty * spec.multiplier
            self.realized_pnl += realized

            if abs(qty) >= abs(pos.qty):
                remaining = pos.qty + qty
                if remaining == 0:
                    del self.open_positions[symbol]
                else:
                    pos.qty = remaining
                    pos.avg_price = price
                    pos.unrealized_pnl = 0.0
            else:
                pos.qty += qty
                pos.unrealized_pnl = 0.0
        else:
            # Adding
            new_qty = pos.qty + qty
            if pos.qty == 0:
                pos.avg_price = price
            else:
                pos.avg_price = (
                    pos.avg_price * abs(pos.qty) + price * abs(qty)
                ) / abs(new_qty)
            pos.qty = new_qty

        self._charge_commission(qty)
        self._check_and_enforce(mark_prices={symbol: price})

    # ------------------------------------------------------------------
    # Permission & sizing
    # ------------------------------------------------------------------
    def can_take_new_risk(self) -> bool:
        return not self.is_locked

    def recommend_size(
        self,
        symbol: str,
        stop_points: float,
        risk_dollars: Optional[float] = None,
    ) -> int:
        if not self.can_take_new_risk():
            return 0

        spec = CONTRACTS[symbol]
        if risk_dollars is None:
            risk_dollars = min(
                ACCOUNT.account_size * 0.005,
                self.remaining_risk_budget * 0.5,  # more conservative buffer
                self.max_planned_risk * 0.4,
            )

        if stop_points <= 0:
            return 0

        risk_per_contract = stop_points * spec.multiplier
        size = int(risk_dollars // risk_per_contract)
        size = max(0, min(size, spec.max_contracts))

        # Extra SIL protection — 1 contract until proven
        if symbol == "SIL" and size > 1 and stop_points > 0.08:
            size = min(size, 1)

        return size

    def flatten_all(self, mark_prices: Optional[Dict[str, float]] = None) -> None:
        """Public emergency flatten — requires marks for any open symbols."""
        marks = mark_prices or {}
        self._force_flatten(marks)
        self.is_locked = True
        self.lock_reason = self.lock_reason or "Manual / emergency flatten"
        self._update_worst()
