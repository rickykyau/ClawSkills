#!/usr/bin/env python3
"""
SMA(50) Crossover - V4: Hybrid approach
- Entry: intraday QQQ cross-up vs previous day's SMA
- SMA Exit: daily close cross-down → exit at first bar next day  
- Stops: checked intraday every 15 min
- T+1 cooldown only after stop exits (QC re-enters same day after SMA exits)
"""
import os
import pandas as pd
import numpy as np

CACHE_DIR = os.path.expanduser("~/clawd/skills/technical-backtesting/cache")
QC_PATH = os.path.expanduser("~/clawd/skills/technical-backtesting/qc_trades.csv")

print("Loading data...", flush=True)
qqq_daily = pd.read_csv(f"{CACHE_DIR}/qqq_daily_adj.csv", index_col=0, parse_dates=True)
tqqq_15 = pd.read_csv(f"{CACHE_DIR}/tqqq_15min_adj.csv", index_col=0, parse_dates=True)
qqq_15 = pd.read_csv(f"{CACHE_DIR}/qqq_15min_adj.csv", index_col=0, parse_dates=True)

qqq_daily.index = pd.to_datetime(qqq_daily.index, utc=True).tz_convert("America/New_York")
tqqq_15.index = pd.to_datetime(tqqq_15.index, utc=True).tz_convert("America/New_York")
qqq_15.index = pd.to_datetime(qqq_15.index, utc=True).tz_convert("America/New_York")

def market_hours(df):
    mins = df.index.hour * 60 + df.index.minute
    return df[(mins >= 9*60+30) & (mins < 16*60)]

tqqq_15 = market_hours(tqqq_15)
qqq_15 = market_hours(qqq_15)

# SMA50
qqq_daily = qqq_daily.sort_index()
qqq_daily["sma50"] = qqq_daily["close"].rolling(50).mean()

# Build SMA lookup
sma_by_date = {}
close_by_date = {}
for idx in qqq_daily.index:
    d = idx.date()
    if not np.isnan(qqq_daily.loc[idx, "sma50"]):
        sma_by_date[d] = qqq_daily.loc[idx, "sma50"]
        close_by_date[d] = qqq_daily.loc[idx, "close"]

# Daily cross-down events (for SMA exits)
sorted_daily = sorted(sma_by_date.keys())
daily_above = {d: close_by_date[d] > sma_by_date[d] for d in sorted_daily}
cross_down_dates = set()  # Dates where daily close crossed below SMA
for i in range(1, len(sorted_daily)):
    prev_d, curr_d = sorted_daily[i-1], sorted_daily[i]
    if daily_above[prev_d] and not daily_above[curr_d]:
        cross_down_dates.add(curr_d)

# Map cross-down to next trading day (exit on next day's first bar)
trading_dates_set = sorted(set(tqqq_15.index.date))
sma_exit_dates = set()
for d in cross_down_dates:
    next_days = [td for td in trading_dates_set if td > d]
    if next_days:
        sma_exit_dates.add(next_days[0])

print(f"SMA exit dates: {len(sma_exit_dates)}", flush=True)

# Pre-group by date
tqqq_by_date = dict(list(tqqq_15.groupby(tqqq_15.index.date)))
qqq_by_date = dict(list(qqq_15.groupby(qqq_15.index.date)))

# Strategy
FIXED_STOP_PCT = 0.075
TRAILING_STOP_PCT = 0.15
capital = 10000.0
shares = 0.0
entry_price = 0.0
highest = 0.0
last_stop_exit_date = None  # T+1 only for stop exits
trades = []
in_position = False
prev_above_sma = None  # For intraday cross-up detection

trading_dates = [d for d in sorted(trading_dates_set) 
                 if pd.Timestamp("2021-01-05").date() <= d <= pd.Timestamp("2026-02-07").date()]

for date in trading_dates:
    day_tqqq = tqqq_by_date.get(date)
    day_qqq = qqq_by_date.get(date)
    if day_tqqq is None or day_qqq is None:
        continue
    
    # Get previous day's SMA
    prev_sma_dates = [sd for sd in sorted_daily if sd < date]
    if not prev_sma_dates:
        continue
    sma_date = max(prev_sma_dates)
    sma_val = sma_by_date[sma_date]
    
    sma_exit_today = date in sma_exit_dates
    sma_exit_done = False
    
    for ts in day_tqqq.index:
        tqqq_close = day_tqqq.loc[ts, "close"]
        tqqq_high = day_tqqq.loc[ts, "high"]
        tqqq_low = day_tqqq.loc[ts, "low"]
        
        # Get QQQ price
        if ts not in qqq_15.index:
            continue
        qqq_price = qqq_15.loc[ts, "close"]
        above_sma = qqq_price > sma_val
        
        if prev_above_sma is None:
            prev_above_sma = above_sma
            continue
        
        # CHECK EXITS
        if in_position:
            if tqqq_high > highest:
                highest = tqqq_high
            
            fixed_stop = entry_price * (1 - FIXED_STOP_PCT)
            trailing_stop = highest * (1 - TRAILING_STOP_PCT)
            active_stop = max(fixed_stop, trailing_stop)
            
            exit_reason = None
            exit_price = None
            
            # SMA exit at first bar of the day
            if sma_exit_today and not sma_exit_done:
                exit_reason = "SMA EXIT"
                exit_price = tqqq_close
                sma_exit_done = True
            # Stop check
            elif tqqq_low <= active_stop:
                exit_reason = "STOP"
                exit_price = active_stop
            
            if exit_reason:
                pnl = shares * (exit_price - entry_price)
                capital = shares * exit_price
                trades[-1].update({
                    "exit_dt": ts, "exit_price": exit_price,
                    "pnl": round(pnl, 2), "exit_reason": exit_reason,
                })
                in_position = False
                shares = 0
                if exit_reason == "STOP":
                    last_stop_exit_date = ts.date()
        
        # CHECK ENTRIES (intraday cross-up)
        elif not prev_above_sma and above_sma:
            if last_stop_exit_date == ts.date():
                prev_above_sma = above_sma
                continue  # T+1 for stop exits only
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

# Close open position
if in_position and trades[-1]["exit_dt"] is None:
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
wins = sum(1 for t in trades if t['pnl'] and t['pnl'] > 0)
losses = sum(1 for t in trades if t['pnl'] and t['pnl'] <= 0)
print(f"My wins: {wins}, losses: {losses}")
print(f"My P&L: ${sum(t['pnl'] for t in trades if t['pnl']):,.2f}")
print(f"QC P&L: ${qc['P&L'].sum():,.2f}")

# Count matches
full_match = 0
entry_match = 0
total = min(len(trades), len(qc))

print(f"\n{'#':>3} | {'My Entry':>12} | {'QC Entry':>12} | {'My Exit':>12} | {'QC Exit':>12} | {'My P&L':>10} | {'QC P&L':>10} | Match | Reason")
print("-" * 115)
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
            full_match += 1
        elif em:
            match = "~"
            entry_match += 1
        else:
            match = "✗"
    
    print(f"{i+1:>3} | {me:>12} | {qe:>12} | {mx:>12} | {qx:>12} | {mp:>10} | {qp:>10} | {match:>5} | {mr}")

print(f"\nFull matches: {full_match}/{total}, Entry-only matches: {entry_match}/{total}")
