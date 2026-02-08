#!/usr/bin/env python3
"""
Best Strategy Detail - SMA(50) Crossover
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

print('Fetching data...')
qqq = fetch('QQQ')
tqqq = fetch('TQQQ')

qqq_d = {t[0]: {'h':t[2], 'l':t[3], 'c':t[4]} for t in qqq}
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

# BEST STRATEGY: SMA(50), Fixed 7.5%, Trail 15%
FIXED_SL = 7.5
TRAIL_SL = 15.0

cap, pos, entry, highest = 10000.0, 0.0, 0.0, 0.0
trades = []
prev_above = None
yearly_vals = {}

for ts in common:
    day = ts.date()
    year = day.year
    
    if day not in sma: continue
    t = tqqq_d[ts]
    above = qqq_d[ts]['c'] > sma[day]
    
    # Track yearly values
    current_val = cap if pos == 0 else pos * t['c']
    if year not in yearly_vals:
        yearly_vals[year] = {'start': current_val, 'trades': 0}
    yearly_vals[year]['end'] = current_val
    
    if pos > 0:
        if t['h'] > highest: highest = t['h']
        
        fixed = entry * (1 - FIXED_SL/100)
        trail = highest * (1 - TRAIL_SL/100)
        stop = max(fixed, trail)
        
        if t['l'] <= stop:
            exit_p = stop
            cap = pos * exit_p
            pnl = (exit_p-entry)/entry*100
            trades.append({'date': str(day), 'pnl': round(pnl,1), 'reason': 'stop', 'year': year})
            yearly_vals[year]['trades'] += 1
            pos, highest = 0, 0
        elif not above and prev_above:
            exit_p = t['c']
            cap = pos * exit_p
            pnl = (exit_p-entry)/entry*100
            trades.append({'date': str(day), 'pnl': round(pnl,1), 'reason': 'sma', 'year': year})
            yearly_vals[year]['trades'] += 1
            pos, highest = 0, 0
    
    elif pos == 0 and above and prev_above == False:
        pos = cap / t['c']
        entry = t['c']
        highest = t['h']
        cap = 0
    
    prev_above = above

if pos > 0:
    last = tqqq_d[common[-1]]
    cap = pos * last['c']
    year = common[-1].year
    trades.append({'date': str(common[-1].date()), 'pnl': round((last['c']-entry)/entry*100,1), 'reason': 'eod', 'year': year})
    yearly_vals[year]['trades'] += 1

print()
print('='*70)
print('BEST STRATEGY: QQQ SMA(50) Crossover -> TQQQ')
print('='*70)
print()
print('STRATEGY RULES')
print('-'*70)
print('Signal Source:      QQQ daily close')
print('Indicator:          50-day Simple Moving Average (SMA)')
print('Trade Asset:        TQQQ (3x leveraged QQQ)')
print('Check Frequency:    Every 15 minutes')
print('Entry:              QQQ crosses ABOVE 50-day SMA')
print('Exit (SMA):         QQQ crosses BELOW 50-day SMA')
print('Fixed Stop Loss:    7.5% below entry price')
print('Trailing Stop:      15% below highest price since entry')
print('Stop Logic:         Hybrid - use whichever stop is HIGHER')
print()
print('='*70)
print('ANNUAL PERFORMANCE')
print('='*70)
print('Year      Start Val      End Val      Return    Trades')
print('-'*70)

years = sorted(yearly_vals.keys())
for y in years:
    v = yearly_vals[y]
    ret = (v['end'] - v['start']) / v['start'] * 100
    print(f"{y}      ${v['start']:>10,.0f}   ${v['end']:>10,.0f}   {ret:>+7.1f}%      {v['trades']}")

total_ret = (cap - 10000) / 10000 * 100
print('-'*70)
print(f"TOTAL     $    10,000   ${cap:>10,.0f}   {total_ret:>+7.1f}%      {len(trades)}")
print()

# Stats
wins = sum(1 for t in trades if t['pnl'] > 0)
stops = len([t for t in trades if t['reason'] == 'stop'])
sma_exits = len([t for t in trades if t['reason'] == 'sma'])
win_pnls = [t['pnl'] for t in trades if t['pnl'] > 0]
loss_pnls = [t['pnl'] for t in trades if t['pnl'] < 0]
avg_win = np.mean(win_pnls) if win_pnls else 0
avg_loss = np.mean(loss_pnls) if loss_pnls else 0

print('='*70)
print('STATISTICS')
print('='*70)
print(f'Total Trades:       {len(trades)}')
print(f'Winning Trades:     {wins} ({wins*100//len(trades)}%)')
print(f'Losing Trades:      {len(trades)-wins} ({(len(trades)-wins)*100//len(trades)}%)')
print(f'Stop-outs:          {stops}')
print(f'SMA Exits:          {sma_exits}')
print(f'Avg Win:            {avg_win:+.1f}%')
print(f'Avg Loss:           {avg_loss:+.1f}%')
if avg_loss != 0:
    print(f'Profit Factor:      {abs(avg_win/avg_loss):.2f}')
print()

print('='*70)
print('ALL TRADES')
print('='*70)
print('Date          P/L     Exit Reason')
print('-'*70)
for t in trades:
    print(f"{t['date']}   {t['pnl']:>+6.1f}%   {t['reason']}")
