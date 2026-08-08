"""Adversarial checks: hard daily loss cannot print past the limit."""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from risk.daily_risk_manager import DailyRiskManager


def test_hard_limit_caps_adverse_mark():
    risk = DailyRiskManager()
    risk.reset_day(date(2025, 6, 1))

    # 10 MES @ $5/pt → 20-point adverse move = -$1,000 before hardening
    risk.record_fill("MES", 10, 5000.0)
    risk.update_unrealized("MES", 4980.0)

    assert risk.is_locked
    assert "HARD" in risk.lock_reason
    assert risk.open_positions == {}
    # Must not print worse than -hard_loss_limit (float tolerance)
    assert risk.total_pnl >= -risk.hard_loss_limit - 1e-6
    assert risk.worst_pnl_today >= -risk.hard_loss_limit - 1e-6


def test_soft_lock_does_not_force_flatten():
    risk = DailyRiskManager()
    risk.reset_day(date(2025, 6, 2))

    # 5 MES, 21-point adverse ≈ -$525 → soft lock, position remains
    risk.record_fill("MES", 5, 5000.0)
    risk.update_unrealized("MES", 4979.0)

    assert risk.is_locked
    assert "SOFT" in risk.lock_reason
    assert "MES" in risk.open_positions
    assert risk.can_take_new_risk() is False


def test_flatten_all_requires_marks():
    risk = DailyRiskManager()
    risk.reset_day(date(2025, 6, 3))
    risk.record_fill("MES", 1, 5000.0)
    try:
        risk.flatten_all()
        assert False, "expected ValueError"
    except ValueError as exc:
        assert "mark price" in str(exc).lower()


if __name__ == "__main__":
    test_hard_limit_caps_adverse_mark()
    test_soft_lock_does_not_force_flatten()
    test_flatten_all_requires_marks()
    print("All risk hard-limit tests passed.")
