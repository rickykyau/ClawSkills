#!/usr/bin/env python3
"""
MACD Deep Test - Focus on MACD variations since it's the winner
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

OUTPUT = os.path.join(script_dir, 'macd_deep_results.jsonl')

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

def backtest(qqq, tqqq, ts, mf, ms, msig, sl, tp):
    n = len(qqq)
    if n < 200: return None
    
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
    
    buy = (macd > sig) & (np.roll(macd,1) <= np.roll(sig,1))
    sell = (macd < sig) & (np.roll(macd,1) >= np.roll(sig,1))
    
    cap, pos, entry, entry_i = 10000.0, 0.0, 0.0, 0
    trades = []
    slp, tpp = sl/100, tp/100
    
    for i in range(50, n):
        if pos > 0:
            pnl = (tqqq[i] - entry) / entry
            if pnl <= -slp or pnl >= tpp or sell[i]:
                cap += pos * tqqq[i]
                trades.append({'e': str(ts[entry_i])[:16], 'x': str(ts[i])[:16], 'p': round(pnl*100,1)})
                pos = 0
        elif buy[i] and cap > 0:
            pos, entry, entry_i, cap = cap/tqqq[i], tqqq[i], i, 0
    
    if pos > 0:
        cap += pos * tqqq[-1]
        trades.append({'e': str(ts[entry_i])[:16], 'x': str(ts[-1])[:16], 
                       'p': round(((tqqq[-1]-entry)/entry)*100,1)})
    
    if len(trades) < 5: return None
    
    ret = (cap - 10000) / 100
    wr = sum(1 for t in trades if t['p'] > 0) / len(trades) * 100
    
    return {'ret': round(ret,1), 'n': len(trades), 'wr': round(wr,0), 't': trades[:3]}

def main():
    print("="*50, flush=True)
    print("MACD DEEP TEST", flush=True)
    print("="*50, flush=True)
    
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
    
    # Extended MACD parameters
    macd_fast = [3, 4, 5, 6, 7, 8, 9, 10, 12, 15]
    macd_slow = [13, 17, 21, 26, 30, 35, 40, 50]
    macd_sig = [3, 5, 7, 9, 11, 13]
    stop_losses = [0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 5.0]
    take_profits = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0, 7.0, 10.0]
    
    total = len(macd_fast) * len(macd_slow) * len(macd_sig) * len(stop_losses) * len(take_profits)
    print(f"\nTotal: {total} combinations", flush=True)
    
    open(OUTPUT, 'w').close()
    
    tested = 0
    valid = 0
    best = {'ret': -999}
    top_10 = []
    
    for mf in macd_fast:
        for ms in macd_slow:
            if mf >= ms: continue  # Invalid
            for msig in macd_sig:
                batch = []
                for sl in stop_losses:
                    for tp in take_profits:
                        tested += 1
                        r = backtest(qqq, tqqq, ts, mf, ms, msig, sl, tp)
                        if r:
                            r['p'] = {'macd': f"{mf}/{ms}/{msig}", 'sl': sl, 'tp': tp}
                            batch.append(r)
                            valid += 1
                            if r['ret'] > best['ret']: best = r
                            top_10.append(r)
                            top_10 = sorted(top_10, key=lambda x: x['ret'], reverse=True)[:10]
                
                if batch:
                    with open(OUTPUT, 'a') as f:
                        for r in batch:
                            f.write(json.dumps(r) + '\n')
                gc.collect()
                
                if tested % 2000 == 0:
                    pct = tested * 100 // total
                    print(f"  {pct}% | {valid} valid | Best: {best['ret']:+.1f}%", flush=True)
    
    print(f"\n{'='*50}", flush=True)
    print(f"DONE: {valid} valid / {total} combinations", flush=True)
    print(f"{'='*50}", flush=True)
    
    print("\n🏆 TOP 10 MACD STRATEGIES:", flush=True)
    for i, r in enumerate(top_10, 1):
        p = r['p']
        print(f"{i:2}. Return: {r['ret']:+6.1f}% | {r['n']:4} trades | Win: {r['wr']:.0f}%", flush=True)
        print(f"    MACD({p['macd']}) | SL:{p['sl']}% TP:{p['tp']}%", flush=True)
        if r['t']:
            print(f"    Sample: {r['t'][0]['e']} → {r['t'][0]['p']:+.1f}%", flush=True)
    
    # Save top 50
    all_r = []
    with open(OUTPUT) as f:
        for line in f:
            all_r.append(json.loads(line))
    top_50 = sorted(all_r, key=lambda x: x['ret'], reverse=True)[:50]
    with open(os.path.join(script_dir, 'macd_top50.json'), 'w') as f:
        json.dump(top_50, f, indent=2)
    
    # Summary
    print(f"\n{'='*50}", flush=True)
    rets = [r['ret'] for r in all_r]
    prof = len([r for r in rets if r > 0])
    print(f"Total: {len(all_r)} | Profitable: {prof} ({prof/len(all_r)*100:.0f}%)", flush=True)
    print(f"Best: {max(rets):+.1f}% | Worst: {min(rets):+.1f}% | Avg: {np.mean(rets):+.1f}%", flush=True)
    print(f"\nSaved to: {OUTPUT}", flush=True)

if __name__ == '__main__':
    main()
