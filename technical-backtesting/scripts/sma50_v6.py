#!/usr/bin/env python3
"""
SMA(50) Crossover - V6: V3 base + EOD exit check.

Key insight from QC trade 33 (Aug 9-10 2023):
- QC enters intraday on cross-up (matching V3)
- But QC ALSO checks daily close vs current day's SMA at end of day
- If daily close < SMA, QC exits at next day's market open
- V3 misses this because it only uses previous day's SMA

Fix: After processing all intraday bars for a day, if in position,
check daily close vs that day's SMA. If bearish, exit at next open.
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
print(f"TQQQ 15m: {len(tqqq_15)}, QQQ 15m: {len(qqq_15)}", flush=True)

qqq_daily = qqq_daily.sort_index()
qqq_daily["sma50"] = qqq_daily["close"].rolling(50).mean()

# Build lookups
sma_by_date = {}  # date -> that day's SMA
daily_close_by_date = {}  # date -> that day's close
prev_sma_by_date = {}  # date -> previous trading day's SMA
sorted_daily_dates = []
for idx in qqq_daily.index:
    d = idx.date()
    if not np.isnan(qqq_daily.loc[idx, "sma50"]):
        sma_by_date[d] = qqq_daily.loc[idx, "sma50"]
        daily_close_by_date[d] = qqq_daily.loc[idx, "close"]
        sorted_daily_dates.append(d)

for i in range(1, len(sorted_daily_dates)):
    prev_sma_by_date[sorted_daily_dates[i]] = sma_by_date[sorted_daily_dates[i-1]]

common_ts = tqqq_15.index.intersection(qqq_15.index).sort_values()

# Precompute last bar per day
last_bar_of_day = {}
for ts in common_ts:
    last_bar_of_day[ts.date()] = ts

# Precompute first bar per day
first_bar_of_day = {}
for ts in common_ts:
    d = ts.date()
    if d not in first_bar_of_day:
        first_bar_of_day[d] = ts

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
pending_eod_exit = False  # Exit at next market open

for ts in common_ts:
    d = ts.date()
    
    if d not in prev_sma_by_date:
        continue
    
    sma_val = prev_sma_by_date[d]  # Previous day's SMA for intraday
    qqq_price = qqq_15.loc[ts, "close"]
    tqqq_close = tqqq_15.loc[ts, "close"]
    tqqq_high = tqqq_15.loc[ts, "high"]
    tqqq_low = tqqq_15.loc[ts, "low"]
    
    above_sma = qqq_price > sma_val
    
    if prev_above_sma is None:
        prev_above_sma = above_sma
        continue
    
    is_first_bar = (ts == first_bar_of_day.get(d))
    
    # Handle pending EOD exit at market open
    if pending_eod_exit and is_first_bar:
        if in_position:
            pnl = shares * (tqqq_close - entry_price)
            capital = shares * tqqq_close
            trades[-1].update({
                "exit_dt": ts, "exit_price": tqqq_close,
                "pnl": round(pnl, 2), "exit_reason": "SMA EXIT (EOD)",
            })
            in_position = False
            shares = 0
            last_exit_date = d
            # After EOD exit, set prev_above_sma based on EOD state
            # The daily close was below SMA, so state should be False
            prev_above_sma = False
        pending_eod_exit = False
        # Don't process entries on this bar (T+1 will handle it anyway for exits)
        # But we still need to update above_sma for subsequent bars
        prev_above_sma = above_sma
        continue
    
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
    
    # EOD check: at last bar of day
    if ts == last_bar_of_day.get(d):
        if d in sma_by_date and d in daily_close_by_date:
            eod_close = daily_close_by_date[d]
            eod_sma = sma_by_date[d]
            eod_above = eod_close > eod_sma
            
            if in_position and not eod_above:
                # Daily close below SMA → exit at next open
                pending_eod_exit = True
            
            # Reset prev_above_sma to EOD state for next day
            prev_above_sma = eod_above

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
print(f"Entry matches: {entry_matches}/{min(len(trades), len(qc))}")
print(f"Total capital: ${capital:,.2f}")
