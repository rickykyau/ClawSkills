#!/usr/bin/env python3
"""
SMA Crossover - CORRECT implementation
- Track highest using HIGH (not close)
- Check stops against LOW
"""

import os
from datetime import datetime, timedelta
import numpy as np
from dotenv import load_dotenv
load_dotenv('/home/ssm-user/clawd/skills/technical-backtesting/.env')

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

def fetch_all(client, symbol):
    all_data = []
    end = datetime.now()
    for i in range(62):
        ce = end - timedelta(days=30*i)
        cs = ce - timedelta(days=30)
        if cs.year < 2020: break
        try:
            req = StockBarsRequest(symbol_or_symbols=symbol, 
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=cs, end=ce, feed='iex')
            bars = client.get_stock_bars(req)
            if bars and symbol in bars.data:
                for b in bars.data[symbol]:
                    all_data.append((b.timestamp, float(b.open), float(b.high), float(b.low), float(b.close)))
        except: continue
    return sorted(set(all_data), key=lambda x: x[0])

print("="*60)
print("SMA CROSSOVER - CORRECT 15-MIN IMPLEMENTATION")
print("="*60)

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

print("\nFetching data...")
qqq = fetch_all(client, 'QQQ')
tqqq = fetch_all(client, 'TQQQ')
print(f"  QQQ: {len(qqq)} bars, TQQQ: {len(tqqq)} bars")

# Align by timestamp (need OHLC)
qqq_d = {t[0]: {'o':t[1], 'h':t[2], 'l':t[3], 'c':t[4]} for t in qqq}
tqqq_d = {t[0]: {'o':t[1], 'h':t[2], 'l':t[3], 'c':t[4]} for t in tqqq}
common = sorted(set(qqq_d.keys()) & set(tqqq_d.keys()))
print(f"  Aligned: {len(common)} bars")
print(f"  Range: {common[0].date()} to {common[-1].date()}")

# Build daily closes for SMA calculation
daily_close = {}
for ts in common:
    d = ts.date()
    daily_close[d] = qqq_d[ts]['c']  # Last close wins

dates = sorted(daily_close.keys())
closes = np.array([daily_close[d] for d in dates])

def test_strategy(sma_period, fixed_sl, trail_sl):
    # Compute SMA
    sma = {}
    for i in range(sma_period, len(dates)):
        sma[dates[i]] = np.mean(closes[i-sma_period:i])
    
    cap = 10000.0
    pos = 0.0
    entry_price = 0.0
    highest_high = 0.0  # Track using HIGH
    trades = []
    prev_above = None
    
    for ts in common:
        day = ts.date()
        if day not in sma: continue
        
        q = qqq_d[ts]
        t = tqqq_d[ts]
        
        above_sma = q['c'] > sma[day]
        
        # Check exits
        if pos > 0:
            # Update highest using HIGH
            if t['h'] > highest_high:
                highest_high = t['h']
            
            fixed_stop = entry_price * (1 - fixed_sl/100)
            trail_stop = highest_high * (1 - trail_sl/100)
            stop = max(fixed_stop, trail_stop)
            
            exited = False
            exit_price = 0
            
            # Check stop against LOW (worst case intraday)
            if t['l'] <= stop:
                exit_price = stop  # Assume filled at stop
                cap = pos * exit_price
                pnl = (exit_price - entry_price) / entry_price * 100
                trades.append({'pnl': round(pnl,1), 'reason': 'stop'})
                exited = True
            # SMA cross down (check at close)
            elif not above_sma and prev_above:
                exit_price = t['c']
                cap = pos * exit_price
                pnl = (exit_price - entry_price) / entry_price * 100
                trades.append({'pnl': round(pnl,1), 'reason': 'sma'})
                exited = True
            
            if exited:
                pos = 0
                highest_high = 0
        
        # Check entry (cross above SMA)
        elif pos == 0 and above_sma and prev_above == False:
            entry_price = t['c']  # Enter at close
            pos = cap / entry_price
            highest_high = t['h']  # Start tracking from this bar's high
            cap = 0
        
        prev_above = above_sma
    
    # Close any open position
    if pos > 0:
        exit_price = tqqq_d[common[-1]]['c']
        cap = pos * exit_price
        pnl = (exit_price - entry_price) / entry_price * 100
        trades.append({'pnl': round(pnl,1), 'reason': 'eod'})
    
    if not trades: return None
    ret = (cap - 10000) / 100
    wins = sum(1 for t in trades if t['pnl'] > 0)
    return {
        'ret': round(ret,1), 
        'n': len(trades), 
        'wr': round(wins/len(trades)*100,0),
        'stops': len([t for t in trades if t['reason'] == 'stop']),
        'trades': trades[:5]  # First 5 for inspection
    }

# Test grid
print("\nTesting strategies...")
results = []
for sma in [50, 100, 150, 200]:
    for fs in [7.5, 10, 12.5, 15]:
        for ts in [12.5, 15, 17.5, 20]:
            r = test_strategy(sma, fs, ts)
            if r:
                r['p'] = {'sma': sma, 'fs': fs, 'ts': ts}
                results.append(r)
    print(f"  SMA({sma}) done")

results.sort(key=lambda x: x['ret'], reverse=True)

print(f"\n{'='*60}")
print("TOP 10 SMA CROSSOVER (CORRECT 15-MIN)")
print(f"{'='*60}\n")

for i, r in enumerate(results[:10], 1):
    p = r['p']
    print(f"{i:2}. Return: {r['ret']:+6.1f}% | {r['n']:3} trades | Win: {r['wr']:.0f}% | Stops: {r['stops']}")
    print(f"    SMA({p['sma']}) Fixed:{p['fs']}% Trail:{p['ts']}%")
    if r.get('trades'):
        print(f"    First trades: {[(t['pnl'], t['reason']) for t in r['trades'][:3]]}")

print(f"\n{'='*60}")
print("BOTTOM 5 (WORST)")  
print(f"{'='*60}")
for r in results[-5:]:
    p = r['p']
    print(f"  {r['ret']:+6.1f}% | {r['n']:3} trades | SMA({p['sma']}) FS:{p['fs']}% TS:{p['ts']}%")

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
prof = len([r for r in results if r['ret'] > 0])
print(f"Profitable: {prof}/{len(results)} ({prof*100//len(results)}%)")
print(f"Best: {results[0]['ret']:+.1f}% | Worst: {results[-1]['ret']:+.1f}%")
avg = np.mean([r['ret'] for r in results])
print(f"Average: {avg:+.1f}%")
