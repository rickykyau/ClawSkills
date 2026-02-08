#!/usr/bin/env python3
"""
Complete Test - Ultra memory-efficient, resumable
Runs in micro-batches, saves after each batch
"""

import os
import json
from datetime import datetime, timedelta
import gc
import numpy as np
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(script_dir), '.env'))

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

OUTPUT = os.path.join(script_dir, 'complete_results.jsonl')
PROGRESS = os.path.join(script_dir, 'progress.json')

def fetch(client, symbol):
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
                    all_data.append((b.timestamp, float(b.close)))
        except: continue
    all_data = sorted(set(all_data), key=lambda x: x[0])
    return [x[0] for x in all_data], np.array([x[1] for x in all_data])

def backtest(qqq, tqqq, ts, mf, ms, msig, sl, tp, strat):
    n = len(qqq)
    if n < 200: return None
    
    # RSI
    delta = np.diff(qqq, prepend=qqq[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_g = np.convolve(gain, np.ones(14)/14, mode='same')
    avg_l = np.convolve(loss, np.ones(14)/14, mode='same')
    with np.errstate(divide='ignore', invalid='ignore'):
        rsi = 100 - 100 / (1 + np.where(avg_l > 0, avg_g/avg_l, 100))
    
    # MACD
    af, asl, asig = 2/(mf+1), 2/(ms+1), 2/(msig+1)
    ef, es = np.zeros(n), np.zeros(n)
    ef[0] = es[0] = qqq[0]
    for i in range(1, n):
        ef[i] = af * qqq[i] + (1-af) * ef[i-1]
        es[i] = asl * qqq[i] + (1-asl) * es[i-1]
    macd = ef - es
    sig = np.zeros(n)
    sig[0] = macd[0]
    for i in range(1, n):
        sig[i] = asig * macd[i] + (1-asig) * sig[i-1]
    
    # Signals
    rb, rs = rsi < 30, rsi > 70
    mb = (macd > sig) & (np.roll(macd,1) <= np.roll(sig,1))
    msl = (macd < sig) & (np.roll(macd,1) >= np.roll(sig,1))
    
    if strat == 'macd':
        buy, sell = mb, msl
    elif strat == 'rsi':
        buy, sell = rb, rs
    else:  # combo
        buy, sell = rb & mb, rs | msl
    
    cap, pos, entry, entry_i = 10000.0, 0.0, 0.0, 0
    trades = []
    slp, tpp = sl/100, tp/100
    
    for i in range(50, n):
        if pos > 0:
            pnl = (tqqq[i] - entry) / entry
            if pnl <= -slp or pnl >= tpp or sell[i]:
                cap += pos * tqqq[i]
                trades.append({'e': str(ts[entry_i])[:16], 'x': str(ts[i])[:16], 'p': round(pnl*100,2)})
                pos = 0
        elif buy[i] and cap > 0:
            pos, entry, entry_i, cap = cap/tqqq[i], tqqq[i], i, 0
    
    if pos > 0:
        cap += pos * tqqq[-1]
        trades.append({'e': str(ts[entry_i])[:16], 'x': str(ts[-1])[:16], 
                       'p': round(((tqqq[-1]-entry)/entry)*100,2)})
    
    if len(trades) < 5: return None
    
    ret = (cap - 10000) / 100
    wr = sum(1 for t in trades if t['p'] > 0) / len(trades) * 100
    
    return {'ret': round(ret,2), 'n': len(trades), 'wr': round(wr,1), 't': trades[:3]}

def main():
    print("="*60, flush=True)
    print("COMPLETE QQQ → TQQQ STRATEGY TEST", flush=True)
    print("="*60, flush=True)
    
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    print("Fetching data...", flush=True)
    qqq_ts, qqq_c = fetch(client, 'QQQ')
    tqqq_ts, tqqq_c = fetch(client, 'TQQQ')
    
    qqq_d = dict(zip(qqq_ts, qqq_c))
    tqqq_d = dict(zip(tqqq_ts, tqqq_c))
    common = sorted(set(qqq_ts) & set(tqqq_ts))
    
    ts = common
    qqq = np.array([qqq_d[t] for t in common])
    tqqq = np.array([tqqq_d[t] for t in common])
    
    print(f"  {len(common)} bars ({common[0].date()} to {common[-1].date()})", flush=True)
    del qqq_d, tqqq_d
    gc.collect()
    
    # Full parameter grid
    macd_fast = [3, 4, 5, 6, 8, 10, 12]
    macd_slow = [17, 21, 26, 30, 35, 40, 50]
    macd_sig = [5, 7, 9, 11, 13]
    stop_losses = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
    take_profits = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0]
    strategies = ['macd', 'rsi', 'combo']
    
    # Generate all param combos
    all_combos = []
    for mf in macd_fast:
        for ms in macd_slow:
            if mf >= ms: continue
            for msig in macd_sig:
                for sl in stop_losses:
                    for tp in take_profits:
                        for strat in strategies:
                            all_combos.append((mf, ms, msig, sl, tp, strat))
    
    total = len(all_combos)
    print(f"Total combinations: {total}", flush=True)
    
    # Load progress
    completed = set()
    if os.path.exists(PROGRESS):
        with open(PROGRESS) as f:
            completed = set(tuple(x) for x in json.load(f))
    
    print(f"Already completed: {len(completed)}", flush=True)
    remaining = [c for c in all_combos if c not in completed]
    print(f"Remaining: {len(remaining)}", flush=True)
    
    if not remaining:
        print("All done!", flush=True)
        return
    
    # Process in micro-batches
    batch_size = 100
    tested = len(completed)
    valid_count = 0
    best = {'ret': -999}
    
    for batch_start in range(0, len(remaining), batch_size):
        batch = remaining[batch_start:batch_start + batch_size]
        batch_results = []
        
        for mf, ms, msig, sl, tp, strat in batch:
            r = backtest(qqq, tqqq, ts, mf, ms, msig, sl, tp, strat)
            if r:
                r['p'] = {'mf': mf, 'ms': ms, 'msig': msig, 'sl': sl, 'tp': tp, 's': strat}
                batch_results.append(r)
                valid_count += 1
                if r['ret'] > best['ret']: best = r
            
            completed.add((mf, ms, msig, sl, tp, strat))
            tested += 1
        
        # Save results
        if batch_results:
            with open(OUTPUT, 'a') as f:
                for r in batch_results:
                    f.write(json.dumps(r) + '\n')
        
        # Save progress
        with open(PROGRESS, 'w') as f:
            json.dump([list(x) for x in completed], f)
        
        gc.collect()
        
        # Report
        pct = tested * 100 // total
        print(f"  {pct}% ({tested}/{total}) | Valid: {valid_count} | Best: {best['ret']:+.1f}%", flush=True)
    
    print(f"\n{'='*60}", flush=True)
    print("COMPLETE!", flush=True)
    print(f"Total tested: {tested}", flush=True)
    print(f"Valid strategies: {valid_count}", flush=True)
    print(f"Best return: {best['ret']:+.1f}%", flush=True)
    print(f"Results saved to: {OUTPUT}", flush=True)

if __name__ == '__main__':
    main()
