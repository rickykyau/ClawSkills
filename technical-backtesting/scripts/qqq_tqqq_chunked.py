#!/usr/bin/env python3
"""
QQQ Signal → TQQQ Trading - Ultra-lightweight chunked version
Writes results to disk immediately after each batch
"""

import os
import sys
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

OUTPUT_FILE = os.path.join(script_dir, 'qqq_tqqq_all_results.jsonl')

def fetch_data(client, symbol):
    """Fetch 5 years of data"""
    all_data = []
    end = datetime.now()
    
    for i in range(62):
        chunk_end = end - timedelta(days=30*i)
        chunk_start = chunk_end - timedelta(days=30)
        if chunk_start.year < 2020:
            break
        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=chunk_start, end=chunk_end, feed='iex'
            )
            bars = client.get_stock_bars(req)
            if bars and symbol in bars.data:
                for b in bars.data[symbol]:
                    all_data.append((b.timestamp, float(b.close)))
        except:
            continue
    
    if not all_data:
        return None, None
    
    # Sort and dedupe
    all_data = sorted(set(all_data), key=lambda x: x[0])
    timestamps = [x[0] for x in all_data]
    closes = np.array([x[1] for x in all_data])
    return timestamps, closes

def backtest(qqq, tqqq, ts, rsi_p, rsi_os, rsi_ob, mf, ms, msig, sl, tp, strat):
    """Fast backtest"""
    n = len(qqq)
    if n < 200:
        return None
    
    # RSI
    delta = np.diff(qqq, prepend=qqq[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    avg_g = np.convolve(gain, np.ones(rsi_p)/rsi_p, mode='same')
    avg_l = np.convolve(loss, np.ones(rsi_p)/rsi_p, mode='same')
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
    rb, rs = rsi < rsi_os, rsi > rsi_ob
    mb = (macd > sig) & (np.roll(macd,1) <= np.roll(sig,1))
    msl = (macd < sig) & (np.roll(macd,1) >= np.roll(sig,1))
    
    if strat == 'rsi':
        buy, sell = rb, rs
    elif strat == 'macd':
        buy, sell = mb, msl
    elif strat == 'both':
        buy, sell = rb & mb, rs | msl
    else:
        buy, sell = rb | mb, rs | msl
    
    # Trade
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
        trades.append({'e': str(ts[entry_i])[:16], 'x': str(ts[-1])[:16], 'p': round(((tqqq[-1]-entry)/entry)*100,1)})
    
    if len(trades) < 3:
        return None
    
    ret = (cap - 10000) / 100
    wr = sum(1 for t in trades if t['p'] > 0) / len(trades) * 100
    
    return {'ret': round(ret,1), 'n': len(trades), 'wr': round(wr,0), 't': trades[:3]}

def main():
    print("=" * 50, flush=True)
    print("QQQ → TQQQ CHUNKED TEST", flush=True)
    print("=" * 50, flush=True)
    
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    print("Fetching data...", flush=True)
    qqq_ts, qqq_c = fetch_data(client, 'QQQ')
    tqqq_ts, tqqq_c = fetch_data(client, 'TQQQ')
    
    # Align
    qqq_dict = dict(zip(qqq_ts, qqq_c))
    tqqq_dict = dict(zip(tqqq_ts, tqqq_c))
    common = sorted(set(qqq_ts) & set(tqqq_ts))
    
    ts = common
    qqq = np.array([qqq_dict[t] for t in common])
    tqqq = np.array([tqqq_dict[t] for t in common])
    
    print(f"  Aligned: {len(common)} bars", flush=True)
    print(f"  Date range: {common[0].date()} to {common[-1].date()}", flush=True)
    
    del qqq_dict, tqqq_dict, qqq_ts, tqqq_ts, qqq_c, tqqq_c
    gc.collect()
    
    # Parameters
    rsi_ps = [5, 7, 9, 14, 21]
    rsi_oss = [15, 20, 25, 30, 35]
    rsi_obs = [65, 70, 75, 80, 85]
    macds = [(8, 17, 9), (8, 21, 9), (12, 26, 9), (5, 35, 5)]
    sls = [0.5, 1.0, 1.5, 2.0, 3.0, 5.0]
    tps = [1.0, 2.0, 3.0, 5.0, 7.0, 10.0]
    strats = ['rsi', 'macd', 'both', 'either']
    
    total = len(rsi_ps) * len(rsi_oss) * len(rsi_obs) * len(macds) * len(sls) * len(tps) * len(strats)
    print(f"\nTotal: {total} combinations", flush=True)
    
    # Clear output file
    open(OUTPUT_FILE, 'w').close()
    
    tested = 0
    valid = 0
    best = {'ret': -999}
    top_10 = []
    
    for rp in rsi_ps:
        for ros in rsi_oss:
            for rob in rsi_obs:
                for mf, ms, msig in macds:
                    batch_results = []
                    
                    for sl in sls:
                        for tp in tps:
                            for strat in strats:
                                tested += 1
                                r = backtest(qqq, tqqq, ts, rp, ros, rob, mf, ms, msig, sl, tp, strat)
                                
                                if r:
                                    r['p'] = {'rp': rp, 'ros': ros, 'rob': rob, 
                                              'macd': f"{mf}/{ms}/{msig}", 'sl': sl, 'tp': tp, 's': strat}
                                    batch_results.append(r)
                                    valid += 1
                                    
                                    if r['ret'] > best['ret']:
                                        best = r
                                    
                                    # Track top 10
                                    top_10.append(r)
                                    top_10 = sorted(top_10, key=lambda x: x['ret'], reverse=True)[:10]
                    
                    # Write batch to disk
                    if batch_results:
                        with open(OUTPUT_FILE, 'a') as f:
                            for r in batch_results:
                                f.write(json.dumps(r) + '\n')
                    
                    gc.collect()
                    
                    # Progress
                    pct = tested * 100 // total
                    if tested % 5000 == 0:
                        print(f"  {pct}% | {valid} valid | Best: {best['ret']:+.1f}%", flush=True)
    
    print(f"\n{'='*50}", flush=True)
    print(f"DONE: {valid} valid / {total} tested", flush=True)
    print(f"{'='*50}", flush=True)
    
    # Results
    print("\n🏆 TOP 10 STRATEGIES:", flush=True)
    for i, r in enumerate(top_10, 1):
        p = r['p']
        print(f"\n{i}. Return: {r['ret']:+.1f}% | {r['n']} trades | Win: {r['wr']:.0f}%", flush=True)
        print(f"   {p['s']:6} | RSI({p['rp']}) OS:{p['ros']} OB:{p['rob']} | MACD({p['macd']})", flush=True)
        print(f"   SL:{p['sl']}% TP:{p['tp']}%", flush=True)
        if r['t']:
            print(f"   Sample: {r['t'][0]['e']} → {r['t'][0]['p']:+.1f}%", flush=True)
    
    # Save top 100 separately
    all_results = []
    with open(OUTPUT_FILE) as f:
        for line in f:
            all_results.append(json.loads(line))
    
    top_100 = sorted(all_results, key=lambda x: x['ret'], reverse=True)[:100]
    with open(os.path.join(script_dir, 'qqq_tqqq_top100.json'), 'w') as f:
        json.dump(top_100, f, indent=2)
    
    # Summary
    print(f"\n{'='*50}", flush=True)
    print("SUMMARY:", flush=True)
    rets = [r['ret'] for r in all_results]
    prof = len([r for r in rets if r > 0])
    print(f"  Total valid: {len(all_results)}", flush=True)
    print(f"  Profitable: {prof} ({prof/len(all_results)*100:.0f}%)", flush=True)
    print(f"  Best: {max(rets):+.1f}% | Worst: {min(rets):+.1f}% | Avg: {np.mean(rets):+.1f}%", flush=True)
    
    print(f"\nResults saved to:", flush=True)
    print(f"  {OUTPUT_FILE}", flush=True)
    print(f"  {os.path.join(script_dir, 'qqq_tqqq_top100.json')}", flush=True)

if __name__ == '__main__':
    main()
