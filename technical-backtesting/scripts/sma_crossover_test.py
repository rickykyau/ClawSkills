#!/usr/bin/env python3
"""
SMA Crossover Strategy Test
QQQ signal → TQQQ trade
"""

import os
import json
from datetime import datetime, timedelta
import numpy as np
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(script_dir), '.env'))

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

def fetch(client, symbol, tf_val, tf_unit):
    all_data = []
    end = datetime.now()
    for i in range(62):
        ce = end - timedelta(days=30*i)
        cs = ce - timedelta(days=30)
        if cs.year < 2020: break
        try:
            req = StockBarsRequest(symbol_or_symbols=symbol, 
                timeframe=TimeFrame(tf_val, tf_unit),
                start=cs, end=ce, feed='iex')
            bars = client.get_stock_bars(req)
            if bars and symbol in bars.data:
                for b in bars.data[symbol]:
                    all_data.append((b.timestamp, float(b.close), float(b.high), float(b.low)))
        except: continue
    all_data = sorted(set(all_data), key=lambda x: x[0])
    return ([x[0] for x in all_data], 
            np.array([x[1] for x in all_data]),
            np.array([x[2] for x in all_data]),
            np.array([x[3] for x in all_data]))

def backtest_sma(qqq_c, tqqq_c, tqqq_h, tqqq_l, ts, sma_period, fixed_sl, trail_sl):
    """
    SMA Crossover strategy:
    - Entry: QQQ crosses above SMA
    - Exit: SMA cross down OR fixed stop OR trailing stop (whichever first)
    """
    n = len(qqq_c)
    if n < sma_period + 50: return None
    
    # Calculate SMA on QQQ
    sma = np.convolve(qqq_c, np.ones(sma_period)/sma_period, mode='valid')
    # Pad to match length
    sma = np.concatenate([np.full(sma_period-1, np.nan), sma])
    
    cap = 10000.0
    pos = 0.0
    entry_price = 0.0
    highest = 0.0
    trades = []
    
    for i in range(sma_period + 1, n):
        if np.isnan(sma[i]) or np.isnan(sma[i-1]):
            continue
            
        # Check exits first
        if pos > 0:
            # Track highest
            if tqqq_h[i] > highest:
                highest = tqqq_h[i]
            
            # Fixed stop (check against low)
            fixed_stop_price = entry_price * (1 - fixed_sl/100)
            # Trailing stop (check against low)
            trail_stop_price = highest * (1 - trail_sl/100)
            # Use higher of the two
            stop_price = max(fixed_stop_price, trail_stop_price)
            
            exit_reason = None
            exit_price = None
            
            # Check if stopped out (use low)
            if tqqq_l[i] <= stop_price:
                exit_price = stop_price
                exit_reason = 'stop'
            # Check SMA cross down (use close)
            elif qqq_c[i] < sma[i] and qqq_c[i-1] >= sma[i-1]:
                exit_price = tqqq_c[i]
                exit_reason = 'sma'
            
            if exit_reason:
                pnl = (exit_price - entry_price) / entry_price * 100
                cap = pos * exit_price
                trades.append({
                    'entry': str(ts[int(entry_i)])[:10],
                    'exit': str(ts[i])[:10],
                    'pnl': round(pnl, 2),
                    'reason': exit_reason
                })
                pos = 0
                highest = 0
        
        # Check entry (QQQ crosses above SMA)
        elif pos == 0 and qqq_c[i] > sma[i] and qqq_c[i-1] <= sma[i-1]:
            pos = cap / tqqq_c[i]
            entry_price = tqqq_c[i]
            entry_i = i
            highest = tqqq_h[i]
            cap = 0
    
    # Close any open position
    if pos > 0:
        pnl = (tqqq_c[-1] - entry_price) / entry_price * 100
        cap = pos * tqqq_c[-1]
        trades.append({
            'entry': str(ts[int(entry_i)])[:10],
            'exit': str(ts[-1])[:10],
            'pnl': round(pnl, 2),
            'reason': 'eod'
        })
    
    if len(trades) < 1: return None
    
    ret = (cap - 10000) / 100
    wins = sum(1 for t in trades if t['pnl'] > 0)
    wr = wins / len(trades) * 100 if trades else 0
    
    return {
        'ret': round(ret, 2),
        'n': len(trades),
        'wr': round(wr, 1),
        'trades': trades
    }

def main():
    print("="*60)
    print("SMA CROSSOVER STRATEGY TEST")
    print("QQQ Signal → TQQQ Trade")
    print("="*60)
    
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    # Test with daily data first (original strategy)
    print("\nFetching DAILY data...")
    qqq_ts, qqq_c, qqq_h, qqq_l = fetch(client, 'QQQ', 1, TimeFrameUnit.Day)
    tqqq_ts, tqqq_c, tqqq_h, tqqq_l = fetch(client, 'TQQQ', 1, TimeFrameUnit.Day)
    
    # Align data
    qqq_d = {t: (c, h, l) for t, c, h, l in zip(qqq_ts, qqq_c, qqq_h, qqq_l)}
    tqqq_d = {t: (c, h, l) for t, c, h, l in zip(tqqq_ts, tqqq_c, tqqq_h, tqqq_l)}
    common = sorted(set(qqq_ts) & set(tqqq_ts))
    
    ts = common
    qqq_c = np.array([qqq_d[t][0] for t in common])
    tqqq_c = np.array([tqqq_d[t][0] for t in common])
    tqqq_h = np.array([tqqq_d[t][1] for t in common])
    tqqq_l = np.array([tqqq_d[t][2] for t in common])
    
    print(f"  {len(common)} daily bars ({common[0].date()} to {common[-1].date()})")
    
    # Parameter grid
    sma_periods = [20, 50, 100, 150, 200]
    fixed_stops = [5, 7.5, 10, 12.5, 15, 20]
    trail_stops = [10, 12.5, 15, 17.5, 20, 25]
    
    results = []
    
    print(f"\nTesting {len(sma_periods) * len(fixed_stops) * len(trail_stops)} combinations...")
    
    for sma in sma_periods:
        for fs in fixed_stops:
            for ts_pct in trail_stops:
                r = backtest_sma(qqq_c, tqqq_c, tqqq_h, tqqq_l, ts, sma, fs, ts_pct)
                if r:
                    r['params'] = {'sma': sma, 'fixed_sl': fs, 'trail_sl': ts_pct}
                    results.append(r)
    
    results.sort(key=lambda x: x['ret'], reverse=True)
    
    print(f"\n{'='*60}")
    print("🏆 TOP 10 SMA CROSSOVER STRATEGIES")
    print(f"{'='*60}\n")
    
    for i, r in enumerate(results[:10], 1):
        p = r['params']
        print(f"{i:2}. Return: {r['ret']:+7.1f}% | {r['n']:3} trades | Win: {r['wr']:.0f}%")
        print(f"    SMA({p['sma']}) | Fixed SL: {p['fixed_sl']}% | Trail SL: {p['trail_sl']}%")
        if r['trades']:
            print(f"    Sample: {r['trades'][0]['entry']} → {r['trades'][0]['exit']} ({r['trades'][0]['pnl']:+.1f}%, {r['trades'][0]['reason']})")
        print()
    
    # Summary
    print(f"{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    prof = len([r for r in results if r['ret'] > 0])
    print(f"Total: {len(results)} | Profitable: {prof} ({prof*100//len(results)}%)")
    print(f"Best: {results[0]['ret']:+.1f}% | Worst: {results[-1]['ret']:+.1f}%")
    
    # Save results
    with open(os.path.join(script_dir, 'sma_crossover_results.json'), 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to sma_crossover_results.json")

if __name__ == '__main__':
    main()
