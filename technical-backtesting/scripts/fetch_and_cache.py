#!/usr/bin/env python3
"""Fetch data from Alpaca and cache to CSV for fast iteration."""
import os, sys
import pandas as pd
from datetime import datetime, timedelta
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from dotenv import load_dotenv

load_dotenv(os.path.expanduser("~/clawd/skills/technical-backtesting/.env"))
client = StockHistoricalDataClient(os.environ["ALPACA_API_KEY"], os.environ["ALPACA_SECRET_KEY"])

CACHE_DIR = os.path.expanduser("~/clawd/skills/technical-backtesting/cache")
os.makedirs(CACHE_DIR, exist_ok=True)

def fetch_bars(symbol, timeframe, start, end, filename, chunk_days=90):
    path = os.path.join(CACHE_DIR, filename)
    if os.path.exists(path):
        print(f"Using cached {filename}")
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        return df
    
    print(f"Fetching {filename}...", flush=True)
    all_bars = []
    current = start
    while current < end:
        next_end = min(current + timedelta(days=chunk_days), end)
        req = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=timeframe,
            start=current,
            end=next_end,
            adjustment='all',
        )
        bars = client.get_stock_bars(req).df
        if len(bars) > 0:
            bars = bars.droplevel("symbol")
            all_bars.append(bars)
            print(f"  {current.date()} to {next_end.date()}: {len(bars)} bars", flush=True)
        current = next_end
    
    if not all_bars:
        print(f"No data for {filename}")
        return pd.DataFrame()
    
    df = pd.concat(all_bars).sort_index()
    df.index = df.index.tz_convert("America/New_York")
    df = df[~df.index.duplicated(keep='first')]
    df.to_csv(path)
    print(f"Cached {filename}: {len(df)} bars", flush=True)
    return df

if __name__ == "__main__":
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if what in ("all", "qqq_daily"):
        fetch_bars("QQQ", TimeFrame.Day, datetime(2020, 10, 1), datetime(2026, 2, 7), "qqq_daily_adj.csv", chunk_days=365)
    
    if what in ("all", "tqqq_15"):
        fetch_bars("TQQQ", TimeFrame(15, TimeFrameUnit.Minute), datetime(2021, 1, 5), datetime(2026, 2, 7), "tqqq_15min_adj.csv", chunk_days=60)
    
    if what in ("all", "qqq_15"):
        fetch_bars("QQQ", TimeFrame(15, TimeFrameUnit.Minute), datetime(2021, 1, 5), datetime(2026, 2, 7), "qqq_15min_adj.csv", chunk_days=60)
    
    print("Done!")
