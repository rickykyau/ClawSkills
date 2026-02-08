#!/usr/bin/env python3
"""SMA(50) Crossover - V2: daily cross detection, intraday stop checks."""
import os
import pandas as pd
import numpy as np

CACHE_DIR = os.path.expanduser("~/clawd/skills/technical-backtesting/cache")
QC_PATH = os.path.expanduser("~/clawd/skills/technical-backtesting/qc_trades.csv")

print("Loading data...", flush=True)
qqq_daily = pd.read_csv(f"{CACHE_DIR}/qqq_daily_adj.csv", index_col=0, parse_dates=True)
tqqq_15 = pd.read_csv(f"{CACHE_DIR}/tqqq_15min_adj.csv", index_col=0, parse_dates=True)

# Ensure proper datetime index  
qqq_daily.index = pd.to_datetime(qqq_daily.index, utc=True).tz_convert("America/New_York")
tqqq_15.index = pd.to_datetime(tqqq_15.index, utc=True).tz_convert("America/New_York")

# Filter to regular market hours only (9:30-16:00 ET)
tqqq_15 = tqqq_15[(tqqq_15.index.hour * 60 + tqqq_15.index.minute >= 9*60+30) & 
                   (tqqq_15.index.hour * 60 + tqqq_15.index.minute < 16*60)]
print(f"TQQQ 15m bars (market hours): {len(tqqq_15)}", flush=True)

# SMA50
qqq_daily = qqq_daily.sort_index()
qqq_daily["sma50"] = qqq_daily["close"].rolling(50).mean()

# Daily signal state
daily_above = {}
for idx in qqq_daily.index:
    row = qqq_daily.loc[idx]
    d = idx.date()
    if not np.isnan(row["sma50"]):
        daily_above[d] = row["close"] > row["sma50"]

# Cross events
sorted_dates = sorted(daily_above.keys())
cross_events = {}
for i in range(1, len(sorted_dates)):
    prev_d, curr_d = sorted_dates[i-1], sorted_dates[i]
    if not daily_above[prev_d] and daily_above[curr_d]:
        cross_events[curr_d] = 'up'
    elif daily_above[prev_d] and not daily_above[curr_d]:
        cross_events[curr_d] = 'down'

print(f"Cross events: {len(cross_events)} ({sum(1 for v in cross_events.values() if v=='up')} up, {sum(1 for v in cross_events.values() if v=='down')} down)", flush=True)

# Pre-group TQQQ by date for fast access
tqqq_15['_date'] = tqqq_15.index.date
grouped = dict(list(tqqq_15.groupby('_date')))

# Strategy
FIXED_STOP_PCT = 0.075
TRAILING_STOP_PCT = 0.15
capital = 10000.0
shares = 0.0
entry_price = 0.0
highest = 0.0
last_exit_date = None
trades = []
in_position = False

# For each cross-up, we want to enter next trading day
# For each cross-down, we want to exit next trading day (SMA exit)
# Stops checked intraday

# Build schedule: for each trading date, what action?
# After a cross-up on date D, enter on D+1 (next trading day)
# After a cross-down on date D, exit on D+1

trading_dates = sorted(grouped.keys())
trading_dates = [d for d in trading_dates if d >= pd.Timestamp("2021-01-05").date() and d <= pd.Timestamp("2026-02-07").date()]

# Map cross events to next trading day actions
entry_dates = set()
sma_exit_dates = set()
for d, ev in cross_events.items():
    # Find next trading day after d
    next_days = [td for td in trading_dates if td > d]
    if next_days:
        if ev == 'up':
            entry_dates.add(next_days[0])
        else:
            sma_exit_dates.add(next_days[0])

# Actually, cross detected at EOD of date D means we should act on D+1
# But actually the cross happens ON date D (today's close vs yesterday's state)
# Let me re-check: cross_events[d] = 'up' means on date d, daily close crossed above SMA
# So we enter on date d+1 (next trading day)

# Wait - actually I think QC might enter on the SAME day the cross is detected.
# Let me check: QC trade 1 entry is 2021-02-23. Let me see what happened with QQQ around then.

print("\nChecking QQQ around first few QC trade entries...", flush=True)
for d in sorted_dates:
    if d >= pd.Timestamp("2021-02-18").date() and d <= pd.Timestamp("2021-02-26").date():
        above = daily_above.get(d, None)
        row = qqq_daily[qqq_daily.index.date == d]
        if len(row) > 0:
            r = row.iloc[0]
            print(f"  {d}: close={r['close']:.2f}, sma50={r['sma50']:.2f}, above={above}")

print("\nRunning backtest...", flush=True)

for date in trading_dates:
    day_bars = grouped.get(date)
    if day_bars is None or len(day_bars) == 0:
        continue
    
    should_enter = date in entry_dates
    should_exit_sma = date in sma_exit_dates
    
    for ts in day_bars.index:
        bar = day_bars.loc[ts]
        price = bar["close"]
        hi = bar["high"]
        lo = bar["low"]
        
        if in_position:
            if hi > highest:
                highest = hi
            
            fixed_stop = entry_price * (1 - FIXED_STOP_PCT)
            trailing_stop = highest * (1 - TRAILING_STOP_PCT)
            active_stop = max(fixed_stop, trailing_stop)
            
            exit_reason = None
            exit_price = None
            
            if lo <= active_stop:
                exit_reason = "STOP"
                exit_price = active_stop
            elif should_exit_sma:
                exit_reason = "SMA EXIT"
                exit_price = price
                should_exit_sma = False  # Only trigger once
            
            if exit_reason:
                pnl = shares * (exit_price - entry_price)
                capital = shares * exit_price
                trades[-1].update({
                    "exit_dt": ts, "exit_price": exit_price,
                    "pnl": round(pnl, 2), "exit_reason": exit_reason,
                })
                in_position = False
                shares = 0
                last_exit_date = ts.date()
                should_enter = False
        
        elif should_enter:
            if last_exit_date == ts.date():
                continue  # T+1
            entry_price = price
            shares = capital / entry_price
            highest = hi
            trades.append({
                "trade_num": len(trades) + 1, "entry_dt": ts,
                "entry_price": entry_price, "exit_dt": None,
                "exit_price": None, "pnl": None, "exit_reason": None,
            })
            in_position = True
            should_enter = False

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
print(f"My wins: {sum(1 for t in trades if t['pnl'] and t['pnl'] > 0)}")
print(f"My P&L: ${sum(t['pnl'] for t in trades if t['pnl']):,.2f}")
print(f"QC P&L: ${qc['P&L'].sum():,.2f}")

print(f"\n{'#':>3} | {'My Entry':>12} | {'QC Entry':>12} | {'My Exit':>12} | {'QC Exit':>12} | {'My P&L':>10} | {'QC P&L':>10} | Match")
print("-" * 105)
for i in range(max(len(trades), len(qc))):
    my = trades[i] if i < len(trades) else None
    qr = qc.iloc[i] if i < len(qc) else None
    me = my["entry_dt"].strftime("%Y-%m-%d") if my else ""
    mx = my["exit_dt"].strftime("%Y-%m-%d") if my and my["exit_dt"] else ""
    mp = f"${my['pnl']:+,.2f}" if my and my['pnl'] else ""
    qe = pd.to_datetime(qr["Entry Time"]).strftime("%Y-%m-%d") if qr is not None else ""
    qx = pd.to_datetime(qr["Exit Time"]).strftime("%Y-%m-%d") if qr is not None else ""
    qp = f"${qr['P&L']:+,.2f}" if qr is not None else ""
    
    match = ""
    if my and qr is not None:
        em = me == qe
        xm = mx == qx
        if not xm and my["exit_dt"]:
            xm = abs((my["exit_dt"].date() if hasattr(my["exit_dt"],'date') else my["exit_dt"]) - pd.to_datetime(qr["Exit Time"]).date()).days <= 1
        pm = (my['pnl'] > 0) == (qr['P&L'] > 0) if my['pnl'] else False
        match = "✓" if em and xm and pm else ("~" if em else "✗")
    
    print(f"{i+1:>3} | {me:>12} | {qe:>12} | {mx:>12} | {qx:>12} | {mp:>10} | {qp:>10} | {match}")
