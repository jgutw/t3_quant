"""One-off Databento connection smoke test. Key comes from .env — never hard-code."""

import databento as db
from dotenv import load_dotenv

load_dotenv()

client = db.Historical()  # reads DATABENTO_API_KEY from environment

# Pull 5 days of continuous front-month MES (volume-based roll) as 1-minute bars
data = client.timeseries.get_range(
    dataset="GLBX.MDP3",  # CME Globex
    symbols="MES.v.0",  # continuous front month (volume roll)
    stype_in="continuous",
    schema="ohlcv-1m",  # 1-minute OHLCV
    start="2025-07-01",
    end="2025-07-05",
)

df = data.to_df()
print(df.head(20))
print(f"\nShape: {df.shape}")
print(f"Columns: {list(df.columns)}")
