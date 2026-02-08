#!/usr/bin/env python3
"""
Fetch/refresh market data cache from Alpaca for SMA50 strategy backtesting.
Fetches QQQ daily, QQQ 15min, and TQQQ 15min data.
"""
import os
import argparse
from datetime import datetime, timedelta
from dotenv import load_dotenv

# Load credentials
ENV_PATH = os.path.expanduser("~/clawd/skills/technical-backtesting/.env")
load_dotenv(ENV_PATH)

ALPACA_API_KEY = os.getenv("ALPACA_API_KEY")
ALPACA_SECRET_KEY = os.getenv("ALPACA_SECRET_KEY")

CACHE_DIR = os.path.expanduser("~/clawd/skills/technical-backtesting/cache")

def fetch_bars(symbol, timeframe, start, end, adjustment="split"):
    """Fetch bars from Alpaca data API."""
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame

    client = StockHistoricalDataClient(ALPACA_API_KEY, ALPACA_SECRET_KEY)

    tf_map = {
        "1Day": TimeFrame.Day,
        "15Min": TimeFrame.Minute,  # We'll handle 15min below
    }

    if timeframe == "15Min":
        from alpaca.data.timeframe import TimeFrame as TF
        tf = TF(15, TF.TimeFrameUnit.Minute)
    else:
        tf = tf_map[timeframe]

    from alpaca.data.enums import Adjustment
    adj_map = {
        "split": Adjustment.SPLIT,
        "all": Adjustment.ALL,
        "raw": Adjustment.RAW,
    }

    request = StockBarsRequest(
        symbol_or_symbols=symbol,
        timeframe=tf,
        start=datetime.fromisoformat(start),
        end=datetime.fromisoformat(end),
        adjustment=adj_map.get(adjustment, Adjustment.SPLIT),
        feed="iex",
    )

    bars = client.get_stock_bars(request)
    df = bars.df
    if isinstance(df.index, pd.MultiIndex):
        df = df.droplevel(0)
    return df

def main():
    import pandas as pd
    global pd

    parser = argparse.ArgumentParser(description="Fetch Alpaca data for SMA50 backtest")
    parser.add_argument("--start", default="2020-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", default=datetime.now().strftime("%Y-%m-%d"), help="End date")
    parser.add_argument("--adjustment", default="split", choices=["split", "all", "raw"])
    args = parser.parse_args()

    os.makedirs(CACHE_DIR, exist_ok=True)

    datasets = [
        ("QQQ", "1Day", "qqq_daily_adj.csv"),
        ("QQQ", "15Min", "qqq_15min_adj.csv"),
        ("TQQQ", "15Min", "tqqq_15min_adj.csv"),
    ]

    for symbol, timeframe, filename in datasets:
        print(f"Fetching {symbol} {timeframe}...", flush=True)
        try:
            df = fetch_bars(symbol, timeframe, args.start, args.end, args.adjustment)
            path = os.path.join(CACHE_DIR, filename)
            df.to_csv(path)
            print(f"  Saved {len(df)} bars to {path}")
        except Exception as e:
            print(f"  ERROR: {e}")

    print("\nDone! Cache refreshed.")

if __name__ == "__main__":
    import pandas as pd
    main()
