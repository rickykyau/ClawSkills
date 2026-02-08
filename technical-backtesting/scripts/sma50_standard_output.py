#!/usr/bin/env python3
"""
SMA(50) Strategy - Standard Output Format
Following sma-daily-trading SKILL.md format
"""

import os
from datetime import datetime, timedelta
import numpy as np
from dotenv import load_dotenv
load_dotenv('/home/ssm-user/clawd/skills/technical-backtesting/.env')

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

client = StockHistoricalDataClient(os.getenv('ALPACA_API_KEY'), os.getenv('ALPACA_SECRET_KEY'))

def fetch(sym):
    data = []
    end = datetime.now()
    for i in range(62):
        ce = end - timedelta(days=30*i)
        cs = ce - timedelta(days=30)
        if cs.year < 2020: break
        try:
            req = StockBarsRequest(symbol_or_symbols=sym, 
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=cs, end=ce, feed='iex')
            bars = client.get_stock_bars(req)
            if bars and sym in bars.data:
                for b in bars.data[sym]:
                    data.append((b.timestamp, b.open, b.high, b.low, b.close))
        except: continue
    return sorted(set(data), key=lambda x: x[0])

# Fetch data
qqq = fetch('QQQ')
tqqq = fetch('TQQQ')

qqq_d = {t[0]: {'o':t[1], 'h':t[2], 'l':t[3], 'c':t[4]} for t in qqq}
tqqq_d = {t[0]: {'o':t[1], 'h':t[2], 'l':t[3], 'c':t[4]} for t in tqqq}
common = sorted(set(qqq_d.keys()) & set(tqqq_d.keys()))

# Daily closes for SMA
daily = {}
for ts in common:
    daily[ts.date()] = qqq_d[ts]['c']
dates = sorted(daily.keys())
closes = np.array([daily[d] for d in dates])

# SMA 50
sma = {}
for i in range(50, len(dates)):
    sma[dates[i]] = np.mean(closes[i-50:i])

# Strategy params
SMA_PERIOD = 50
FIXED_SL = 7.5
TRAIL_SL = 15.0
STARTING_CAP = 10000.0

# Run backtest
cap = STARTING_CAP
pos = 0.0
entry_price = 0.0
highest = 0.0
entry_date = None
entry_time = None
trades = []
prev_above = None

for ts in common:
    day = ts.date()
    if day not in sma: continue
    
    t = tqqq_d[ts]
    above = qqq_d[ts]['c'] > sma[day]
    
    if pos > 0:
        if t['h'] > highest: highest = t['h']
        
        fixed = entry_price * (1 - FIXED_SL/100)
        trail = highest * (1 - TRAIL_SL/100)
        stop = max(fixed, trail)
        
        exit_reason = None
        exit_price = None
        
        if t['l'] <= stop:
            exit_price = stop
            exit_reason = 'TRAIL' if trail >= fixed else 'FIXED'
        elif not above and prev_above:
            exit_price = t['c']
            exit_reason = 'SMA'
        
        if exit_reason:
            pnl_pct = (exit_price - entry_price) / entry_price * 100
            pnl_dollar = pos * exit_price - (pos * entry_price)
            cap = pos * exit_price
            trades.append({
                'entry_date': entry_date,
                'entry_time': entry_time,
                'exit_date': day,
                'exit_time': str(ts.time())[:5],
                'entry_price': entry_price,
                'exit_price': exit_price,
                'pnl_pct': pnl_pct,
                'pnl_dollar': pnl_dollar,
                'exit_reason': exit_reason,
                'entry_type': 'CROSS'
            })
            pos, highest = 0, 0
    
    elif pos == 0 and above and prev_above == False:
        pos = cap / t['c']
        entry_price = t['c']
        entry_date = day
        entry_time = str(ts.time())[:5]
        highest = t['h']
        cap = 0
    
    prev_above = above

# Close any open position
if pos > 0:
    last = tqqq_d[common[-1]]
    exit_price = last['c']
    pnl_pct = (exit_price - entry_price) / entry_price * 100
    pnl_dollar = pos * exit_price - (pos * entry_price)
    cap = pos * exit_price
    trades.append({
        'entry_date': entry_date,
        'entry_time': entry_time,
        'exit_date': common[-1].date(),
        'exit_time': str(common[-1].time())[:5],
        'entry_price': entry_price,
        'exit_price': exit_price,
        'pnl_pct': pnl_pct,
        'pnl_dollar': pnl_dollar,
        'exit_reason': 'OPEN',
        'entry_type': 'CROSS'
    })

# Calculate B&H QQQ
first_qqq = qqq_d[common[0]]['c']
last_qqq = qqq_d[common[-1]]['c']
bh_return = (last_qqq - first_qqq) / first_qqq * 100

# Stats
wins = [t for t in trades if t['pnl_pct'] > 0]
losses = [t for t in trades if t['pnl_pct'] <= 0]
fixed_stops = len([t for t in trades if t['exit_reason'] == 'FIXED'])
trail_stops = len([t for t in trades if t['exit_reason'] == 'TRAIL'])
sma_exits = len([t for t in trades if t['exit_reason'] == 'SMA'])

# Output in standard format
print()
print("=" * 80)
print(" STRATEGY: QQQ Signal -> TQQQ Trade (with Hybrid Stop Loss)")
print("=" * 80)
print()
print("| Rule           | Value                                                        |")
print("|----------------|--------------------------------------------------------------|")
print(f"| Signal Source  | QQQ daily close                                              |")
print(f"| Indicator      | {SMA_PERIOD}-day SMA                                                   |")
print(f"| Trade Asset    | TQQQ (3x leveraged)                                          |")
print(f"| Check Freq     | Every 15 minutes                                             |")
print(f"| Fixed Stop     | {FIXED_SL}% from entry price                                         |")
print(f"| Trailing Stop  | {TRAIL_SL}% from highest price                                       |")
print(f"| STOP LOGIC     | Use whichever stop is HIGHER (loses less)                    |")
print(f"| BUY            | QQQ crosses above {SMA_PERIOD} SMA                                     |")
print(f"| SELL           | QQQ crosses below {SMA_PERIOD} SMA OR stop hit                         |")
print()
print(f"Period: {common[0].date()} to {common[-1].date()}")
print(f"Starting Capital: ${STARTING_CAP:,.0f}")
print()

print("TRADE LOG")
print("-" * 100)
print(f"{'#':<4} {'Entry Date':<12} {'Entry Time':<12} {'Exit Date':<12} {'Exit Time':<10} {'Entry$':<9} {'Exit$':<9} {'P&L%':<8} {'P&L$':<9} {'Exit':<6} {'Entry':<6}")
print("-" * 100)

for i, t in enumerate(trades, 1):
    print(f"{i:<4} {str(t['entry_date']):<12} {t['entry_time']:<12} {str(t['exit_date']):<12} {t['exit_time']:<10} ${t['entry_price']:<8.2f} ${t['exit_price']:<8.2f} {t['pnl_pct']:>+6.1f}% ${t['pnl_dollar']:>+8.0f} {t['exit_reason']:<6} {t['entry_type']:<6}")

print()
print("FINAL RESULTS")
print("-" * 80)
total_return = (cap - STARTING_CAP) / STARTING_CAP * 100
alpha = total_return - bh_return
print(f"Strategy Final:     ${cap:,.0f} ({total_return:+.1f}%)")
print(f"B&H QQQ Final:      ${STARTING_CAP * (1 + bh_return/100):,.0f} ({bh_return:+.1f}%)")
print(f"Alpha vs QQQ:       {alpha:+.1f}%")
print()
print(f"Total Trades:       {len(trades)}")
print(f"  - CROSS entries:  {len(trades)}")
print(f"  - REENTRY:        0")
print(f"  - 20DAY entries:  0")
print()
print("Exit Breakdown:")
print(f"  - Fixed Stop:     {fixed_stops}")
print(f"  - Trailing Stop:  {trail_stops}")
print(f"  - SMA Exit:       {sma_exits}")
print()
win_rate = len(wins) / len(trades) * 100 if trades else 0
avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0
print(f"Win Rate:           {win_rate:.0f}% ({len(wins)}/{len(trades)})")
print(f"Avg Win:            {avg_win:+.1f}%")
print(f"Avg Loss:           {avg_loss:+.1f}%")

# Annual breakdown
print()
print("ANNUAL PERFORMANCE")
print("-" * 80)
yearly = {}
for t in trades:
    y = t['exit_date'].year
    if y not in yearly:
        yearly[y] = {'pnl': 0, 'trades': 0}
    yearly[y]['pnl'] += t['pnl_dollar']
    yearly[y]['trades'] += 1

running = STARTING_CAP
for y in sorted(yearly.keys()):
    start = running
    running += yearly[y]['pnl']
    ret = (running - start) / start * 100
    print(f"{y}: ${start:>10,.0f} -> ${running:>10,.0f} ({ret:>+6.1f}%) | {yearly[y]['trades']} trades")
