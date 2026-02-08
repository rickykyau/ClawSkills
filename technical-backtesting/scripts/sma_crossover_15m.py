#!/usr/bin/env python3
"""
SMA Crossover Strategy - 15 MINUTE DATA
Proper stop loss checking against intraday lows
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

def fetch_15m(client, symbol):
    """Fetch 15-min bars with OHLC"""
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
    all_data = sorted(set(all_data), key=lambda x: x[0])
    return all_data

def compute_daily_sma(bars_15m, sma_period):
    """
    Compute daily SMA from 15-min data
    Returns dict: date -> sma value (using previous day's close)
    """
    # Group by date and get daily close (last bar of day)
    daily_closes = {}
    for ts, o, h, l, c in bars_15m:
        d = ts.date()
        daily_closes[d] = c  # Last close of the day
    
    dates = sorted(daily_closes.keys())
    closes = [daily_closes[d] for d in dates]
    
    # Compute SMA
    sma_dict = {}
    for i in range(sma_period, len(dates)):
        avg = np.mean(closes[i-sma_period:i])
        # SMA for today is based on previous N days (not including today)
        sma_dict[dates[i]] = avg
    
    return sma_dict, daily_closes

def backtest_sma_15m(qqq_bars, tqqq_bars, sma_period, fixed_sl, trail_sl):
    """
    SMA Crossover with 15-min execution
    - Entry: QQQ daily close crosses above SMA → enter next bar
    - Exit: Check stops every 15 min, also check SMA cross
    """
    # Compute daily SMA from QQQ
    sma_dict, qqq_daily = compute_daily_sma(qqq_bars, sma_period)
    
    # Create aligned 15-min dict for TQQQ
    tqqq_dict = {b[0]: {'o': b[1], 'h': b[2], 'l': b[3], 'c': b[4]} for b in tqqq_bars}
    
    # Get common timestamps
    qqq_ts = [b[0] for b in qqq_bars]
    common_ts = sorted(set(qqq_ts) & set(tqqq_dict.keys()))
    
    if len(common_ts) < 1000: return None
    
    cap = 10000.0
    pos = 0.0
    entry_price = 0.0
    highest = 0.0
    entry_date = None
    trades = []
    
    prev_day = None
    prev_qqq_close = None
    prev_sma = None
    
    for ts in common_ts:
        day = ts.date()
        tqqq = tqqq_dict[ts]
        
        # Get today's SMA (computed from prior days)
        sma = sma_dict.get(day)
        if sma is None:
            continue
        
        # Track QQQ daily close for signal
        qqq_bar = next((b for b in qqq_bars if b[0] == ts), None)
        if qqq_bar is None:
            continue
        qqq_close = qqq_bar[4]
        
        # Check exits first (every 15-min bar)
        if pos > 0:
            # Update highest with this bar's high
            if tqqq['h'] > highest:
                highest = tqqq['h']
            
            # Calculate stops
            fixed_stop_price = entry_price * (1 - fixed_sl/100)
            trail_stop_price = highest * (1 - trail_sl/100)
            stop_price = max(fixed_stop_price, trail_stop_price)
            
            exit_reason = None
            exit_price = None
            
            # Check stop against LOW (realistic execution)
            if tqqq['l'] <= stop_price:
                exit_price = stop_price  # Assume we get filled at stop
                exit_reason = 'stop'
            # Check SMA cross (at end of day)
            elif prev_day and day != prev_day:
                # New day - check if yesterday closed below SMA
                if prev_qqq_close and prev_sma and prev_qqq_close < prev_sma:
                    exit_price = tqqq['o']  # Exit at open of new day
                    exit_reason = 'sma'
            
            if exit_reason:
                pnl = (exit_price - entry_price) / entry_price * 100
                cap = pos * exit_price
                trades.append({
                    'entry': str(entry_date),
                    'exit': str(day),
                    'pnl': round(pnl, 2),
                    'reason': exit_reason
                })
                pos = 0
                highest = 0
                entry_date = None
        
        # Check entry (only at day change, after SMA cross confirmed)
        if pos == 0 and prev_day and day != prev_day:
            # Check if yesterday QQQ closed above SMA (and prev day was below)
            if (prev_qqq_close and prev_sma and prev_qqq_close > prev_sma):
                # Get day before yesterday's close
                day_before = prev_day - timedelta(days=1)
                day_before_close = qqq_daily.get(day_before)
                day_before_sma = sma_dict.get(prev_day)  # SMA for prev_day uses older data
                
                # True crossover: was below, now above
                if day_before_close and day_before_sma and day_before_close <= day_before_sma:
                    pos = cap / tqqq['o']
                    entry_price = tqqq['o']
                    entry_date = day
                    highest = tqqq['h']
                    cap = 0
        
        # Update for next iteration
        if prev_day != day:
            prev_sma = sma
            prev_qqq_close = qqq_close
        prev_day = day
    
    # Close any open position
    if pos > 0:
        last_bar = tqqq_dict[common_ts[-1]]
        pnl = (last_bar['c'] - entry_price) / entry_price * 100
        cap = pos * last_bar['c']
        trades.append({
            'entry': str(entry_date),
            'exit': str(common_ts[-1].date()),
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
    print("SMA CROSSOVER - 15 MINUTE DATA (REALISTIC)")
    print("Stops checked against intraday lows")
    print("="*60)
    
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    print("\nFetching 15-min data...")
    qqq_bars = fetch_15m(client, 'QQQ')
    tqqq_bars = fetch_15m(client, 'TQQQ')
    
    print(f"  QQQ: {len(qqq_bars)} bars")
    print(f"  TQQQ: {len(tqqq_bars)} bars")
    print(f"  Date range: {qqq_bars[0][0].date()} to {qqq_bars[-1][0].date()}")
    
    # Parameter grid
    sma_periods = [20, 50, 100, 150, 200]
    fixed_stops = [5, 7.5, 10, 12.5, 15, 20]
    trail_stops = [10, 12.5, 15, 17.5, 20, 25]
    
    results = []
    
    print(f"\nTesting {len(sma_periods) * len(fixed_stops) * len(trail_stops)} combinations...")
    
    for sma in sma_periods:
        for fs in fixed_stops:
            for ts_pct in trail_stops:
                r = backtest_sma_15m(qqq_bars, tqqq_bars, sma, fs, ts_pct)
                if r:
                    r['params'] = {'sma': sma, 'fixed_sl': fs, 'trail_sl': ts_pct}
                    results.append(r)
        print(f"  SMA({sma}) done...")
    
    if not results:
        print("No valid results!")
        return
    
    results.sort(key=lambda x: x['ret'], reverse=True)
    
    print(f"\n{'='*60}")
    print("🏆 TOP 10 SMA CROSSOVER (15-MIN DATA)")
    print(f"{'='*60}\n")
    
    for i, r in enumerate(results[:10], 1):
        p = r['params']
        print(f"{i:2}. Return: {r['ret']:+7.1f}% | {r['n']:3} trades | Win: {r['wr']:.0f}%")
        print(f"    SMA({p['sma']}) | Fixed SL: {p['fixed_sl']}% | Trail SL: {p['trail_sl']}%")
        if r['trades']:
            print(f"    Sample: {r['trades'][0]['entry']} → {r['trades'][0]['exit']} ({r['trades'][0]['pnl']:+.1f}%, {r['trades'][0]['reason']})")
        print()
    
    # Also show worst
    print(f"\n{'='*60}")
    print("BOTTOM 5 (WORST)")
    print(f"{'='*60}\n")
    for i, r in enumerate(results[-5:], 1):
        p = r['params']
        print(f"{i}. Return: {r['ret']:+7.1f}% | {r['n']:3} trades | SMA({p['sma']}) FS:{p['fixed_sl']}% TS:{p['trail_sl']}%")
    
    # Summary
    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'='*60}")
    prof = len([r for r in results if r['ret'] > 0])
    print(f"Total: {len(results)} | Profitable: {prof} ({prof*100//len(results) if results else 0}%)")
    if results:
        print(f"Best: {results[0]['ret']:+.1f}% | Worst: {results[-1]['ret']:+.1f}%")
        avg = np.mean([r['ret'] for r in results])
        print(f"Average: {avg:+.1f}%")
    
    # Save results
    with open(os.path.join(script_dir, 'sma_crossover_15m_results.json'), 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to sma_crossover_15m_results.json")

if __name__ == '__main__':
    main()
