"""
Quick example of how the pieces fit together.
Replace the synthetic data with real continuous contracts once the data pipeline is live.
"""

import pandas as pd
import numpy as np
from risk import DailyRiskManager
from strategies import WeightedEnsembleStrategy
from backtest import SimpleBacktester
from data.continuous import add_session_start


def make_synthetic_mes(n_bars: int = 2000) -> pd.DataFrame:
    """Generate a simple random-walk series that looks roughly like MES."""
    np.random.seed(42)
    dates = pd.date_range("2025-01-01 09:30", periods=n_bars, freq="5min")
    # crude RTH filter
    dates = dates[(dates.time >= pd.Timestamp("09:30").time()) &
                  (dates.time <= pd.Timestamp("16:00").time())]

    returns = np.random.normal(0, 0.0008, len(dates))
    close = 5200 * np.exp(np.cumsum(returns))
    high = close * (1 + np.abs(np.random.normal(0, 0.0004, len(dates))))
    low = close * (1 - np.abs(np.random.normal(0, 0.0004, len(dates))))
    open_ = close.copy()
    volume = np.random.randint(500, 5000, len(dates))

    df = pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)
    df = add_session_start(df)
    return df


if __name__ == "__main__":
    print("Building synthetic MES data...")
    data = make_synthetic_mes(1500)

    risk = DailyRiskManager()
    strategy = WeightedEnsembleStrategy(
        risk_manager=risk,
        use_adaptive_weights=True,
        min_accuracy=0.48,
        multi_tf_agreement=0.75,
        require_cpr_filter=False,   # no CPR on synthetic
        require_orb_filter=False,
    )

    bt = SimpleBacktester(
        strategy=strategy,
        risk_manager=risk,
        symbol="MES",
        stop_points=6.0,
    )

    print("Running backtest (this is only a smoke test on synthetic data)...")
    result = bt.run(data)

    print(f"\nFinal PnL:     ${result.final_pnl:,.2f}")
    print(f"Max Drawdown:  ${result.max_dd:,.2f}")
    print(f"Trades:        {result.num_trades}")
    print(f"Locked days:   {result.locked_out_days}")
    print("\nScaffolding is ready. Open the t3_quant folder in Cursor and start iterating.")
