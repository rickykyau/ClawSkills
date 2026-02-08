#!/usr/bin/env python3
"""
SMA(50) Crossover Strategy - Full Trade List
Uses Alpaca real data, checks every 15 minutes.
Signal: QQQ vs 50-day SMA → Trade: TQQQ
"""

import os
import sys
import pandas as pd
import numpy as np
from datetime import datetime, timedelta, time as dtime
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

# Load env
from dotenv import load_dotenv
load_dotenv(os.path.expanduser("~/clawd/skills/technical-backtesting/.env"))

API_KEY = os.environ["ALPACA_API_KEY"]
SECRET_KEY = os.environ["ALPACA_SECRET_KEY"]

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

# ══════════════════════════════════════════════════════════════
# FETCH DATA
# ══════════════════════════════════════════════════════════════
print("Fetching QQQ daily bars for SMA...")
qqq_daily_req = StockBarsRequest(
    symbol_or_symbols="QQQ",
    timeframe=TimeFrame.Day,
    start=datetime(2020, 10, 1),  # Extra early for SMA warmup
    end=datetime(2026, 2, 7),
)
qqq_daily = client.get_stock_bars(qqq_daily_req).df
qqq_daily = qqq_daily.droplevel("symbol")
qqq_daily.index = qqq_daily.index.tz_convert("America/New_York")
qqq_daily = qqq_daily.sort_index()

# Calculate 50-day SMA
qqq_daily["sma50"] = qqq_daily["close"].rolling(50).mean()
print(f"QQQ daily bars: {len(qqq_daily)}, SMA ready from: {qqq_daily.dropna(subset=['sma50']).index[0].date()}")

# Build daily SMA lookup (date -> sma value, close)
sma_lookup = {}
for idx, row in qqq_daily.iterrows():
    d = idx.date()
    if not np.isnan(row["sma50"]):
        sma_lookup[d] = {"sma": row["sma50"], "close": row["close"]}

print("\nFetching TQQQ 15-min bars (this may take a moment)...")
# Fetch in chunks to avoid limits
all_tqqq = []
chunk_start = datetime(2021, 1, 5)
chunk_end = datetime(2026, 2, 7)

# Fetch in 6-month chunks
current = chunk_start
while current < chunk_end:
    next_end = min(current + timedelta(days=180), chunk_end)
    req = StockBarsRequest(
        symbol_or_symbols="TQQQ",
        timeframe=TimeFrame(15, TimeFrameUnit.Minute),
        start=current,
        end=next_end,
    )
    bars = client.get_stock_bars(req).df
    if len(bars) > 0:
        bars = bars.droplevel("symbol")
        all_tqqq.append(bars)
        print(f"  Chunk {current.date()} to {next_end.date()}: {len(bars)} bars")
    current = next_end

tqqq = pd.concat(all_tqqq).sort_index()
tqqq.index = tqqq.index.tz_convert("America/New_York")
# Remove duplicates
tqqq = tqqq[~tqqq.index.duplicated(keep='first')]
print(f"TQQQ 15-min bars total: {len(tqqq)}")

# Also fetch QQQ 15-min for intraday signal checking
print("\nFetching QQQ 15-min bars...")
all_qqq_15 = []
current = chunk_start
while current < chunk_end:
    next_end = min(current + timedelta(days=180), chunk_end)
    req = StockBarsRequest(
        symbol_or_symbols="QQQ",
        timeframe=TimeFrame(15, TimeFrameUnit.Minute),
        start=current,
        end=next_end,
    )
    bars = client.get_stock_bars(req).df
    if len(bars) > 0:
        bars = bars.droplevel("symbol")
        all_qqq_15.append(bars)
        print(f"  Chunk {current.date()} to {next_end.date()}: {len(bars)} bars")
    current = next_end

qqq_15 = pd.concat(all_qqq_15).sort_index()
qqq_15.index = qqq_15.index.tz_convert("America/New_York")
qqq_15 = qqq_15[~qqq_15.index.duplicated(keep='first')]
print(f"QQQ 15-min bars total: {len(qqq_15)}")

# ══════════════════════════════════════════════════════════════
# RUN STRATEGY
# ══════════════════════════════════════════════════════════════
print("\n" + "=" * 80)
print("RUNNING STRATEGY...")
print("=" * 80)

# Strategy params
SMA_PERIOD = 50
FIXED_STOP_PCT = 0.075   # 7.5%
TRAILING_STOP_PCT = 0.15  # 15%
STARTING_CAPITAL = 10000

capital = STARTING_CAPITAL
shares = 0
entry_price = 0
highest_since_entry = 0
prev_above_sma = None
last_exit_date = None
trades = []
trade_num = 0

# Get sorted unique dates from TQQQ data
trading_dates = sorted(set(tqqq.index.date))

for date in trading_dates:
    # Get previous trading day's SMA
    # We use the PREVIOUS day's daily close vs SMA for the signal
    prev_dates = [d for d in sma_lookup.keys() if d < date]
    if not prev_dates:
        continue
    prev_date = max(prev_dates)
    sma_data = sma_lookup[prev_date]
    prev_close = sma_data["close"]
    prev_sma = sma_data["sma"]
    
    # Initialize prev_above_sma
    if prev_above_sma is None:
        prev_above_sma = prev_close > prev_sma
        continue
    
    # Get today's 15-min bars
    day_tqqq = tqqq[tqqq.index.date == date]
    day_qqq = qqq_15[qqq_15.index.date == date]
    
    if len(day_tqqq) == 0 or len(day_qqq) == 0:
        continue
    
    for ts in day_tqqq.index:
        # Get TQQQ bar data
        tqqq_bar = tqqq.loc[ts]
        tqqq_close = tqqq_bar["close"]
        tqqq_high = tqqq_bar["high"]
        tqqq_low = tqqq_bar["low"]
        
        # Get QQQ price at same timestamp
        if ts in qqq_15.index:
            qqq_price = qqq_15.loc[ts]["close"]
        else:
            continue
        
        # Current signal: QQQ price vs previous day's SMA
        above_sma = qqq_price > prev_sma
        
        # ── CHECK EXITS ──
        if shares > 0:
            # Update highest
            if tqqq_high > highest_since_entry:
                highest_since_entry = tqqq_high
            
            fixed_stop = entry_price * (1 - FIXED_STOP_PCT)
            trailing_stop = highest_since_entry * (1 - TRAILING_STOP_PCT)
            active_stop = max(fixed_stop, trailing_stop)
            
            exit_reason = None
            exit_price = None
            
            # Stop hit?
            if tqqq_low <= active_stop:
                exit_reason = "TRAIL STOP" if trailing_stop >= fixed_stop else "FIXED STOP"
                exit_price = active_stop  # Fill at stop price
            # SMA cross down?
            elif prev_above_sma == True and above_sma == False:
                exit_reason = "SMA EXIT"
                exit_price = tqqq_close
            
            if exit_reason:
                pnl_amount = shares * (exit_price - entry_price)
                pnl_pct = (exit_price - entry_price) / entry_price * 100
                capital = shares * exit_price
                
                days_held = (ts.date() - trades[-1]["entry_dt"].date()).days if trades else 0
                # Update last trade with exit info
                trades[-1].update({
                    "exit_dt": ts,
                    "exit_price": round(exit_price, 2),
                    "pnl_amount": round(pnl_amount, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "days_held": days_held,
                    "exit_reason": exit_reason,
                })
                
                shares = 0
                entry_price = 0
                highest_since_entry = 0
                last_exit_date = ts.date()
        
        # ── CHECK ENTRIES ──
        else:
            if last_exit_date == ts.date():
                pass  # T+1 cooldown
            elif prev_above_sma == False and above_sma == True:
                trade_num += 1
                entry_price = tqqq_close
                shares = capital / entry_price
                highest_since_entry = tqqq_high
                
                trades.append({
                    "trade_num": trade_num,
                    "entry_dt": ts,
                    "entry_price": round(entry_price, 2),
                    "exit_dt": None,
                    "exit_price": None,
                    "pnl_amount": None,
                    "pnl_pct": None,
                    "days_held": None,
                    "exit_reason": None,
                })
        
        prev_above_sma = above_sma

# Handle open position
if shares > 0 and trades and trades[-1]["exit_dt"] is None:
    last_price = tqqq.iloc[-1]["close"]
    pnl_amount = shares * (last_price - entry_price)
    pnl_pct = (last_price - entry_price) / entry_price * 100
    days_held = (tqqq.index[-1].date() - trades[-1]["entry_dt"].date()).days
    trades[-1].update({
        "exit_dt": tqqq.index[-1],
        "exit_price": round(last_price, 2),
        "pnl_amount": round(pnl_amount, 2),
        "pnl_pct": round(pnl_pct, 2),
        "days_held": days_held,
        "exit_reason": "OPEN",
    })
    capital = shares * last_price

# ══════════════════════════════════════════════════════════════
# OUTPUT
# ══════════════════════════════════════════════════════════════
print("\n")
print(f"{'#':>3} | {'Entry DateTime':>19} | {'Exit DateTime':>19} | {'Entry$':>8} | {'Exit$':>8} | {'P&L $':>10} | {'P&L %':>7} | {'Days':>4} | Exit Reason")
print("-" * 120)

for t in trades:
    entry_str = t["entry_dt"].strftime("%Y-%m-%d %H:%M") if t["entry_dt"] else ""
    exit_str = t["exit_dt"].strftime("%Y-%m-%d %H:%M") if t["exit_dt"] else ""
    pnl_str = f"${t['pnl_amount']:>+,.2f}" if t["pnl_amount"] is not None else ""
    pnl_pct_str = f"{t['pnl_pct']:>+.2f}%" if t["pnl_pct"] is not None else ""
    
    print(f"{t['trade_num']:>3} | {entry_str:>19} | {exit_str:>19} | ${t['entry_price']:>7.2f} | ${t['exit_price'] or 0:>7.2f} | {pnl_str:>10} | {pnl_pct_str:>7} | {t['days_held'] or 0:>4} | {t['exit_reason'] or ''}")

print("-" * 120)
print(f"\nTotal Trades: {len(trades)}")
wins = [t for t in trades if t["pnl_pct"] and t["pnl_pct"] > 0]
losses = [t for t in trades if t["pnl_pct"] and t["pnl_pct"] <= 0]
print(f"Wins: {len(wins)} | Losses: {len(losses)} | Win Rate: {len(wins)/len(trades)*100:.1f}%" if trades else "")
print(f"Starting Capital: ${STARTING_CAPITAL:,.2f}")
print(f"Final Capital: ${capital:,.2f}")
print(f"Total Return: {(capital/STARTING_CAPITAL - 1)*100:+.2f}%")

if wins:
    print(f"Avg Win: {sum(t['pnl_pct'] for t in wins)/len(wins):+.2f}%")
if losses:
    print(f"Avg Loss: {sum(t['pnl_pct'] for t in losses)/len(losses):+.2f}%")
