#!/usr/bin/env python3
"""
Simple SMA Crossover - 15 MIN DATA
Minimal memory, fast execution
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
                    all_data.append((b.timestamp, float(b.close), float(b.low)))
        except: continue
    return sorted(set(all_data), key=lambda x: x[0])

print("="*60)
print("SMA CROSSOVER - 15 MINUTE DATA")
print("="*60)

client = StockHistoricalDataClient(API_KEY, SECRET_KEY)

print("\nFetching data...")
qqq = fetch_all(client, 'QQQ')
tqqq = fetch_all(client, 'TQQQ')
print(f"  QQQ: {len(qqq)} bars, TQQQ: {len(tqqq)} bars")

# Align by timestamp
qqq_d = {t[0]: (t[1], t[2]) for t in qqq}
tqqq_d = {t[0]: (t[1], t[2]) for t in tqqq}
common = sorted(set(qqq_d.keys()) & set(tqqq_d.keys()))
print(f"  Aligned: {len(common)} bars")
print(f"  Range: {common[0].date()} to {common[-1].date()}")

# Build daily closes for SMA calculation
daily_close = {}
for ts in common:
    d = ts.date()
    daily_close[d] = qqq_d[ts][0]  # Last close wins

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
    highest = 0.0
    trades = []
    prev_above = None
    
    for ts in common:
        day = ts.date()
        if day not in sma: continue
        
        qqq_close = qqq_d[ts][0]
        tqqq_close = tqqq_d[ts][0]
        tqqq_low = tqqq_d[ts][1]
        
        above_sma = qqq_close > sma[day]
        
        # Check exits
        if pos > 0:
            if tqqq_close > highest:
                highest = tqqq_close
            
            fixed_stop = entry_price * (1 - fixed_sl/100)
            trail_stop = highest * (1 - trail_sl/100)
            stop = max(fixed_stop, trail_stop)
            
            exited = False
            if tqqq_low <= stop:  # Stop hit
                cap = pos * stop
                trades.append(((stop - entry_price)/entry_price*100, 'stop'))
                exited = True
            elif not above_sma and prev_above:  # SMA cross down
                cap = pos * tqqq_close
                trades.append(((tqqq_close - entry_price)/entry_price*100, 'sma'))
                exited = True
            
            if exited:
                pos = 0
                highest = 0
        
        # Check entry (cross above)
        elif pos == 0 and above_sma and prev_above == False:
            pos = cap / tqqq_close
            entry_price = tqqq_close
            highest = tqqq_close
            cap = 0
        
        prev_above = above_sma
    
    if pos > 0:
        cap = pos * tqqq_d[common[-1]][0]
        trades.append(((tqqq_d[common[-1]][0] - entry_price)/entry_price*100, 'eod'))
    
    if not trades: return None
    ret = (cap - 10000) / 100
    wins = sum(1 for t in trades if t[0] > 0)
    return {'ret': round(ret,1), 'n': len(trades), 'wr': round(wins/len(trades)*100,0)}

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
print("TOP 10 SMA CROSSOVER (15-MIN STOPS)")
print(f"{'='*60}\n")

for i, r in enumerate(results[:10], 1):
    p = r['p']
    print(f"{i:2}. Return: {r['ret']:+6.1f}% | {r['n']:3} trades | Win: {r['wr']:.0f}%")
    print(f"    SMA({p['sma']}) Fixed:{p['fs']}% Trail:{p['ts']}%")

print(f"\n{'='*60}")
print("SUMMARY")
print(f"{'='*60}")
prof = len([r for r in results if r['ret'] > 0])
print(f"Profitable: {prof}/{len(results)} ({prof*100//len(results)}%)")
print(f"Best: {results[0]['ret']:+.1f}% | Worst: {results[-1]['ret']:+.1f}%")
