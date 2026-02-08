#!/usr/bin/env python3
"""
SMA(50) Crossover - V5: Dual check matching QC behavior.

Key insight: QC uses Daily resolution SMA which updates at market close.
- During the day: compare QQQ 15-min price vs PREVIOUS day's SMA
- At end of day: compare QQQ daily close vs CURRENT day's SMA
- If EOD signal flips, execute at next day's market open

This dual-check explains why QC has fewer trades than pure intraday detection.
"""
import os
import pandas as pd
import numpy as np
from datetime import time as dtime

CACHE_DIR = os.path.expanduser("~/clawd/skills/technical-backtesting/cache")
QC_PATH = os.path.expanduser("~/clawd/skills/technical-backtesting/qc_trades.csv")

print("Loading data...", flush=True)
qqq_daily = pd.read_csv(f"{CACHE_DIR}/qqq_daily_adj.csv", index_col=0, parse_dates=True)
tqqq_15 = pd.read_csv(f"{CACHE_DIR}/tqqq_15min_adj.csv", index_col=0, parse_dates=True)
qqq_15 = pd.read_csv(f"{CACHE_DIR}/qqq_15min_adj.csv", index_col=0, parse_dates=True)

qqq_daily.index = pd.to_datetime(qqq_daily.index, utc=True).tz_convert("America/New_York")
tqqq_15.index = pd.to_datetime(tqqq_15.index, utc=True).tz_convert("America/New_York")
qqq_15.index = pd.to_datetime(qqq_15.index, utc=True).tz_convert("America/New_York")

# Market hours filter
def market_hours(df):
    h, m = df.index.hour, df.index.minute
    mins = h * 60 + m
    return df[(mins >= 9*60+30) & (mins < 16*60)]

tqqq_15 = market_hours(tqqq_15)
qqq_15 = market_hours(qqq_15)

# SMA50 on daily
qqq_daily = qqq_daily.sort_index()
qqq_daily["sma50"] = qqq_daily["close"].rolling(50).mean()

# Build lookups
# Previous day's SMA for intraday checks
prev_sma = {}  # date -> previous trading day's SMA
daily_sma = {}  # date -> that day's SMA (for EOD check)
daily_close = {}  # date -> that day's close
dates_sorted = qqq_daily.index.tolist()
for i, idx in enumerate(dates_sorted):
    d = idx.date()
    if not np.isnan(qqq_daily.loc[idx, "sma50"]):
        daily_sma[d] = qqq_daily.loc[idx, "sma50"]
        daily_close[d] = qqq_daily.loc[idx, "close"]
        if i > 0:
            prev_d = dates_sorted[i-1].date()
            if prev_d in daily_sma:
                prev_sma[d] = daily_sma[prev_d]

print(f"TQQQ 15m: {len(tqqq_15)}, QQQ 15m: {len(qqq_15)}", flush=True)

# Strategy params
FIXED_STOP_PCT = 0.075
TRAILING_STOP_PCT = 0.15
capital = 10000.0
shares = 0.0
entry_price = 0.0
highest = 0.0
last_exit_date = None
trades = []
in_position = False
prev_above_sma = None  # State for intraday cross detection

# Track EOD signal state separately
eod_above_sma = None  # Based on daily close vs daily SMA
pending_eod_exit = False  # If EOD check says exit, do it at next open

# Get common timestamps
common_ts = tqqq_15.index.intersection(qqq_15.index).sort_values()
trading_dates = sorted(set(common_ts.date))

print(f"Common timestamps: {len(common_ts)}", flush=True)
print(f"Trading dates: {len(trading_dates)}", flush=True)

# Initialize EOD state from data before backtest start
for d in sorted(daily_sma.keys()):
    if d >= pd.Timestamp("2021-01-05").date():
        break
    if d in daily_close and d in daily_sma:
        eod_above_sma = daily_close[d] > daily_sma[d]

# Precompute last bar per day
last_bar_of_day = {}
for ts in common_ts:
    last_bar_of_day[ts.date()] = ts

for ts in common_ts:
    d = ts.date()
    
    if d not in prev_sma:
        continue
    
    sma_val = prev_sma[d]  # Previous day's SMA for intraday
    qqq_price = qqq_15.loc[ts, "close"]
    tqqq_close = tqqq_15.loc[ts, "close"]
    tqqq_high = tqqq_15.loc[ts, "high"]
    tqqq_low = tqqq_15.loc[ts, "low"]
    
    above_sma = qqq_price > sma_val
    
    if prev_above_sma is None:
        prev_above_sma = above_sma
        continue
    
    is_market_open = (ts.hour == 9 and ts.minute == 30)
    
    # CHECK: Pending EOD exit at market open
    if pending_eod_exit and is_market_open and in_position:
        pnl = shares * (tqqq_close - entry_price)
        capital = shares * tqqq_close
        trades[-1].update({
            "exit_dt": ts, "exit_price": tqqq_close,
            "pnl": round(pnl, 2), "exit_reason": "SMA EXIT (EOD)",
        })
        in_position = False
        shares = 0
        last_exit_date = d
        pending_eod_exit = False
    
    # CHECK: Pending EOD entry at market open
    if not in_position and pending_eod_exit == "entry" and is_market_open:
        if last_exit_date != d:  # T+1
            entry_price = tqqq_close
            shares = capital / entry_price
            highest = tqqq_high
            trades.append({
                "trade_num": len(trades) + 1, "entry_dt": ts,
                "entry_price": entry_price, "exit_dt": None,
                "exit_price": None, "pnl": None, "exit_reason": None,
            })
            in_position = True
        pending_eod_exit = False
    
    if isinstance(pending_eod_exit, str):
        pending_eod_exit = False
    
    # CHECK EXITS (intraday)
    if in_position:
        if tqqq_high > highest:
            highest = tqqq_high
        
        fixed_stop = entry_price * (1 - FIXED_STOP_PCT)
        trailing_stop = highest * (1 - TRAILING_STOP_PCT)
        active_stop = max(fixed_stop, trailing_stop)
        
        exit_reason = None
        exit_price = None
        
        if tqqq_low <= active_stop:
            exit_reason = "STOP"
            exit_price = active_stop
        elif prev_above_sma and not above_sma:
            exit_reason = "SMA EXIT"
            exit_price = tqqq_close
        
        if exit_reason:
            pnl = shares * (exit_price - entry_price)
            capital = shares * exit_price
            trades[-1].update({
                "exit_dt": ts, "exit_price": exit_price,
                "pnl": round(pnl, 2), "exit_reason": exit_reason,
            })
            in_position = False
            shares = 0
            last_exit_date = d
    
    # CHECK ENTRIES (intraday)
    elif not prev_above_sma and above_sma:
        if last_exit_date == d:
            prev_above_sma = above_sma
            continue  # T+1
        entry_price = tqqq_close
        shares = capital / entry_price
        highest = tqqq_high
        trades.append({
            "trade_num": len(trades) + 1, "entry_dt": ts,
            "entry_price": entry_price, "exit_dt": None,
            "exit_price": None, "pnl": None, "exit_reason": None,
        })
        in_position = True
    
    prev_above_sma = above_sma
    
    # End of day check: last bar of the day
    if d in last_bar_of_day and ts == last_bar_of_day[d]:
        # Last bar of day - do EOD check
        if d in daily_sma and d in daily_close:
            new_eod = daily_close[d] > daily_sma[d]
            if eod_above_sma is not None:
                if in_position and eod_above_sma and not new_eod:
                    # Signal flipped bearish at EOD - exit at next open
                    pending_eod_exit = True
                elif not in_position and not eod_above_sma and new_eod:
                    # Signal flipped bullish at EOD - enter at next open
                    pending_eod_exit = "entry"
            eod_above_sma = new_eod
            # Also reset intraday state to match EOD
            prev_above_sma = new_eod

# Close open position
if in_position and trades and trades[-1]["exit_dt"] is None:
    last_price = tqqq_15.iloc[-1]["close"]
    pnl = shares * (last_price - entry_price)
    trades[-1].update({
        "exit_dt": tqqq_15.index[-1], "exit_price": last_price,
        "pnl": round(pnl, 2), "exit_reason": "OPEN",
    })
    capital = shares * last_price

# ══════════════ COMPARE WITH QC ══════════════
qc = pd.read_csv(QC_PATH)
print(f"\nMy trades: {len(trades)}, QC trades: {len(qc)}")
wins = [t for t in trades if t['pnl'] and t['pnl'] > 0]
losses = [t for t in trades if t['pnl'] and t['pnl'] <= 0]
print(f"My wins: {len(wins)}, losses: {len(losses)}")
print(f"My P&L: ${sum(t['pnl'] for t in trades if t['pnl']):,.2f}")
print(f"QC P&L: ${qc['P&L'].sum():,.2f}")

full_matches = 0
entry_matches = 0

print(f"\n{'#':>3} | {'My Entry':>12} | {'QC Entry':>12} | {'My Exit':>12} | {'QC Exit':>12} | {'My P&L':>10} | {'QC P&L':>10} | Match | Reason")
print("-" * 120)
for i in range(max(len(trades), len(qc))):
    my = trades[i] if i < len(trades) else None
    qr = qc.iloc[i] if i < len(qc) else None
    me = my["entry_dt"].strftime("%Y-%m-%d") if my else ""
    mx = my["exit_dt"].strftime("%Y-%m-%d") if my and my["exit_dt"] else ""
    mp = f"${my['pnl']:+,.2f}" if my and my['pnl'] else ""
    mr = my["exit_reason"] if my else ""
    qe = pd.to_datetime(qr["Entry Time"]).strftime("%Y-%m-%d") if qr is not None else ""
    qx = pd.to_datetime(qr["Exit Time"]).strftime("%Y-%m-%d") if qr is not None else ""
    qp = f"${qr['P&L']:+,.2f}" if qr is not None else ""
    
    match = ""
    if my and qr is not None:
        em = me == qe
        xm = mx == qx or (my["exit_dt"] and abs((my["exit_dt"].date() - pd.to_datetime(qr["Exit Time"]).date()).days) <= 1)
        pm = (my['pnl'] > 0) == (qr['P&L'] > 0) if my['pnl'] else False
        if em and xm and pm:
            match = "✓"
            full_matches += 1
        elif em:
            match = "~"
            entry_matches += 1
        else:
            match = "✗"
    
    print(f"{i+1:>3} | {me:>12} | {qe:>12} | {mx:>12} | {qx:>12} | {mp:>10} | {qp:>10} | {match:>5} | {mr}")

print("-" * 120)
print(f"\nFull matches: {full_matches}/{min(len(trades), len(qc))}")
print(f"Entry-only matches: {entry_matches}/{min(len(trades), len(qc))}")
print(f"Total capital: ${capital:,.2f}")
