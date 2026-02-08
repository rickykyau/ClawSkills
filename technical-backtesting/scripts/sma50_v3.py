#!/usr/bin/env python3
"""SMA(50) Crossover - V3: intraday QQQ cross detection against daily SMA."""
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

# Filter to regular market hours (9:30-16:00 ET)
def market_hours(df):
    mins = df.index.hour * 60 + df.index.minute
    return df[(mins >= 9*60+30) & (mins < 16*60)]

tqqq_15 = market_hours(tqqq_15)
qqq_15 = market_hours(qqq_15)
print(f"TQQQ 15m: {len(tqqq_15)}, QQQ 15m: {len(qqq_15)}", flush=True)

# SMA50 on daily
qqq_daily = qqq_daily.sort_index()
qqq_daily["sma50"] = qqq_daily["close"].rolling(50).mean()

# Build SMA lookup: date -> SMA value (from that day's calculation)
sma_by_date = {}
for idx in qqq_daily.index:
    d = idx.date()
    if not np.isnan(qqq_daily.loc[idx, "sma50"]):
        sma_by_date[d] = qqq_daily.loc[idx, "sma50"]

# Merge QQQ and TQQQ on common timestamps
common_ts = tqqq_15.index.intersection(qqq_15.index)
print(f"Common timestamps: {len(common_ts)}", flush=True)

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
prev_above_sma = None

# Iterate through common timestamps
for ts in common_ts.sort_values():
    d = ts.date()
    
    # Get SMA for previous trading day
    prev_sma_dates = [sd for sd in sma_by_date.keys() if sd < d]
    if not prev_sma_dates:
        continue
    # Use the most recent SMA before today
    sma_date = max(prev_sma_dates)
    sma_val = sma_by_date[sma_date]
    
    qqq_price = qqq_15.loc[ts, "close"]
    tqqq_close = tqqq_15.loc[ts, "close"]
    tqqq_high = tqqq_15.loc[ts, "high"]
    tqqq_low = tqqq_15.loc[ts, "low"]
    
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
            last_exit_date = ts.date()
    
    # CHECK ENTRIES
    elif not prev_above_sma and above_sma:
        if last_exit_date == ts.date():
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
    mr = my["exit_reason"] if my else ""
    qe = pd.to_datetime(qr["Entry Time"]).strftime("%Y-%m-%d") if qr is not None else ""
    qx = pd.to_datetime(qr["Exit Time"]).strftime("%Y-%m-%d") if qr is not None else ""
    qp = f"${qr['P&L']:+,.2f}" if qr is not None else ""
    
    match = ""
    if my and qr is not None:
        em = me == qe
        xm = mx == qx or (my["exit_dt"] and abs((my["exit_dt"].date() - pd.to_datetime(qr["Exit Time"]).date()).days) <= 1)
        pm = (my['pnl'] > 0) == (qr['P&L'] > 0) if my['pnl'] else False
        match = "✓" if em and xm and pm else ("~" if em else "✗")
    
    print(f"{i+1:>3} | {me:>12} | {qe:>12} | {mx:>12} | {qx:>12} | {mp:>10} | {qp:>10} | {match} {mr}")
