"""
V1 gate ablation: same 5m MES setup, four gate combinations.

  1. Full     — MTF ON  + CPR ON   (original V1)
  2. MTF only — MTF ON  + CPR OFF
  3. CPR only — MTF OFF + CPR ON
  4. Neither  — MTF OFF + CPR OFF  (raw equal-weight ensemble)

Usage:
  python -m backtest.run_v1_ablation
"""

from __future__ import annotations

import logging
from pathlib import Path

import pandas as pd

from backtest.run_v1 import OUT_DIR, run_v1

# Risk-manager CRITICAL logs are noisy across four runs; keep warnings visible.
logging.getLogger("risk.daily_risk_manager").setLevel(logging.ERROR)

VARIANTS = [
    ("full", True, True),
    ("mtf_only", True, False),
    ("cpr_only", False, True),
    ("neither", False, False),
]


def main() -> None:
    rows = []
    print("V1 ablation — preparing data once, then four gate variants...\n")

    for name, use_mtf, use_cpr in VARIANTS:
        print(f"--- {name} ---")
        out = run_v1(
            use_mtf=use_mtf,
            use_cpr=use_cpr,
            tag=f"v1_ablation_{name}",
            save=True,
            quiet=False,
        )
        m = out["metrics"]
        rows.append(
            {
                "variant": name,
                "mtf": use_mtf,
                "cpr": use_cpr,
                "final_pnl": m["final_pnl"],
                "max_dd": m["max_drawdown"],
                "trades": m["num_trades"],
                "trades_per_day": m["trades_per_day"],
                "win_rate": m["win_rate"],
                "expectancy": m["expectancy_per_trade"],
                "avg_win": m["avg_win"],
                "avg_loss": m["avg_loss"],
                "profit_factor": m["profit_factor"],
                "locked_days": m["locked_out_days"],
            }
        )
        print()

    summary = pd.DataFrame(rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / "v1_ablation_summary.csv"
    summary.to_csv(csv_path, index=False)

    # Compact comparison table for the terminal
    show = summary.copy()
    show["final_pnl"] = show["final_pnl"].map(lambda x: f"${x:,.2f}")
    show["max_dd"] = show["max_dd"].map(lambda x: f"${x:,.2f}")
    show["expectancy"] = show["expectancy"].map(lambda x: f"${x:,.2f}")
    show["win_rate"] = show["win_rate"].map(lambda x: f"{x:.1%}")
    show["trades_per_day"] = show["trades_per_day"].map(lambda x: f"{x:.2f}")
    show["profit_factor"] = show["profit_factor"].map(
        lambda x: f"{x:.2f}" if x is not None else "n/a"
    )

    print("=== Ablation summary ===")
    print(
        show[
            [
                "variant",
                "final_pnl",
                "profit_factor",
                "expectancy",
                "win_rate",
                "trades_per_day",
                "trades",
                "max_dd",
                "locked_days",
            ]
        ].to_string(index=False)
    )
    print(f"\nSaved -> {csv_path}")


if __name__ == "__main__":
    main()
