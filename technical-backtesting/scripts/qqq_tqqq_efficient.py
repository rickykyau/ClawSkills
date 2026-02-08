#!/usr/bin/env python3
"""
QQQ Signal → TQQQ Trading - Memory Efficient Version
Processes in micro-batches, saves results incrementally
"""

import os
import sys
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')
import gc

import pandas as pd
import numpy as np
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(os.path.dirname(script_dir), '.env'))

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

def fetch_data(client, symbol, days=1825):  # 5 years
    """Fetch data in chunks"""
    all_data = []
    end = datetime.now()
    
    for i in range(62):  # ~5 years in monthly chunks
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
                    all_data.append({
                        'ts': b.timestamp,
                        'c': float(b.close),
                        'v': int(b.volume)
                    })
        except:
            continue
    
    if not all_data:
        return None
    
    df = pd.DataFrame(all_data)
    df['ts'] = pd.to_datetime(df['ts'])
    df = df.drop_duplicates(subset='ts').set_index('ts').sort_index()
    return df

def fast_backtest(qqq_close, tqqq_close, timestamps, rsi_p, rsi_os, rsi_ob, 
                  macd_f, macd_s, macd_sig, sl, tp, strategy):
    """Ultra-fast numpy-based backtest"""
    n = len(qqq_close)
    if n < 200:
        return None
    
    # RSI
    delta = np.diff(qqq_close, prepend=qqq_close[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    
    # Simple moving average for RSI
    avg_gain = np.convolve(gain, np.ones(rsi_p)/rsi_p, mode='same')
    avg_loss = np.convolve(loss, np.ones(rsi_p)/rsi_p, mode='same')
    
    with np.errstate(divide='ignore', invalid='ignore'):
        rs = np.where(avg_loss > 0, avg_gain / avg_loss, 100)
        rsi = 100 - (100 / (1 + rs))
    
    # MACD (simplified EMA)
    alpha_f = 2 / (macd_f + 1)
    alpha_s = 2 / (macd_s + 1)
    alpha_sig = 2 / (macd_sig + 1)
    
    ema_f = np.zeros(n)
    ema_s = np.zeros(n)
    ema_f[0] = ema_s[0] = qqq_close[0]
    
    for i in range(1, n):
        ema_f[i] = alpha_f * qqq_close[i] + (1 - alpha_f) * ema_f[i-1]
        ema_s[i] = alpha_s * qqq_close[i] + (1 - alpha_s) * ema_s[i-1]
    
    macd = ema_f - ema_s
    macd_signal = np.zeros(n)
    macd_signal[0] = macd[0]
    for i in range(1, n):
        macd_signal[i] = alpha_sig * macd[i] + (1 - alpha_sig) * macd_signal[i-1]
    
    # Signals
    rsi_buy = rsi < rsi_os
    rsi_sell = rsi > rsi_ob
    macd_buy = (macd > macd_signal) & (np.roll(macd, 1) <= np.roll(macd_signal, 1))
    macd_sell = (macd < macd_signal) & (np.roll(macd, 1) >= np.roll(macd_signal, 1))
    
    if strategy == 'rsi':
        buy, sell = rsi_buy, rsi_sell
    elif strategy == 'macd':
        buy, sell = macd_buy, macd_sell
    elif strategy == 'both':
        buy = rsi_buy & macd_buy
        sell = rsi_sell | macd_sell
    else:  # either
        buy = rsi_buy | macd_buy
        sell = rsi_sell | macd_sell
    
    # Simulate
    capital = 10000.0
    pos = 0.0
    entry = 0.0
    entry_idx = 0
    trades = []
    sl_pct = sl / 100
    tp_pct = tp / 100
    
    for i in range(50, n):
        if pos > 0:
            pnl_pct = (tqqq_close[i] - entry) / entry
            if pnl_pct <= -sl_pct or pnl_pct >= tp_pct or sell[i]:
                capital += pos * tqqq_close[i]
                trades.append({
                    'entry': str(timestamps[entry_idx]),
                    'exit': str(timestamps[i]),
                    'pnl_pct': round(pnl_pct * 100, 2)
                })
                pos = 0
        elif buy[i] and capital > 0:
            pos = capital / tqqq_close[i]
            entry = tqqq_close[i]
            entry_idx = i
            capital = 0
    
    if pos > 0:
        final = tqqq_close[-1]
        capital += pos * final
        trades.append({
            'entry': str(timestamps[entry_idx]),
            'exit': str(timestamps[-1]),
            'pnl_pct': round(((final - entry) / entry) * 100, 2)
        })
    
    if not trades:
        return None
    
    total_ret = (capital - 10000) / 100
    wins = sum(1 for t in trades if t['pnl_pct'] > 0)
    
    return {
        'ret': round(total_ret, 2),
        'trades': len(trades),
        'wr': round(wins / len(trades) * 100, 0),
        'sample': trades[:3]  # First 3 trades for validation
    }

def main():
    print("=" * 60, flush=True)
    print("QQQ → TQQQ MASSIVE STRATEGY TEST", flush=True)
    print("=" * 60, flush=True)
    
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    print("\nFetching 5 years of data...", flush=True)
    qqq = fetch_data(client, 'QQQ')
    print(f"  QQQ: {len(qqq)} bars", flush=True)
    
    tqqq = fetch_data(client, 'TQQQ')
    print(f"  TQQQ: {len(tqqq)} bars", flush=True)
    
    # Align data
    common_idx = qqq.index.intersection(tqqq.index)
    qqq_close = qqq.loc[common_idx, 'c'].values
    tqqq_close = tqqq.loc[common_idx, 'c'].values
    timestamps = common_idx.tolist()
    
    print(f"  Aligned: {len(common_idx)} bars ({common_idx[0].date()} to {common_idx[-1].date()})", flush=True)
    
    # Clear memory
    del qqq, tqqq
    gc.collect()
    
    # Parameters
    rsi_periods = [5, 7, 9, 12, 14, 18, 21, 25]
    rsi_os = [15, 20, 25, 30, 35]
    rsi_ob = [65, 70, 75, 80, 85]
    macd_settings = [(5, 13, 6), (8, 17, 9), (8, 21, 9), (12, 26, 9), (12, 26, 12), (5, 35, 5)]
    stop_losses = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0, 5.0]
    take_profits = [1.0, 1.5, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0, 15.0]
    strategies = ['rsi', 'macd', 'both', 'either']
    
    total = len(rsi_periods) * len(rsi_os) * len(rsi_ob) * len(macd_settings) * \
            len(stop_losses) * len(take_profits) * len(strategies)
    
    print(f"\nTotal combinations: {total}", flush=True)
    print("\nTesting...", flush=True)
    
    results = []
    tested = 0
    last_report = 0
    
    output_file = os.path.join(script_dir, 'qqq_tqqq_results.json')
    
    for rp in rsi_periods:
        for ros in rsi_os:
            for rob in rsi_ob:
                for mf, ms, msig in macd_settings:
                    for sl in stop_losses:
                        for tp in take_profits:
                            for strat in strategies:
                                tested += 1
                                
                                r = fast_backtest(
                                    qqq_close, tqqq_close, timestamps,
                                    rp, ros, rob, mf, ms, msig, sl, tp, strat
                                )
                                
                                if r and r['trades'] >= 3:
                                    r['params'] = {
                                        'rsi_p': rp, 'rsi_os': ros, 'rsi_ob': rob,
                                        'macd': f"{mf}/{ms}/{msig}",
                                        'sl': sl, 'tp': tp, 'strat': strat
                                    }
                                    results.append(r)
                                
                                # Progress every 10%
                                pct = tested * 100 // total
                                if pct >= last_report + 10:
                                    last_report = pct
                                    print(f"  {pct}% ({len(results)} valid)", flush=True)
                                    
                                    # Save intermediate results
                                    if len(results) > 0:
                                        top_so_far = sorted(results, key=lambda x: x['ret'], reverse=True)[:10]
                                        with open(output_file, 'w') as f:
                                            json.dump(top_so_far, f, indent=2)
                                    gc.collect()
    
    print(f"\n{'='*60}", flush=True)
    print(f"COMPLETED: {len(results)} valid out of {total} tested", flush=True)
    print(f"{'='*60}", flush=True)
    
    if not results:
        print("No valid results!")
        return
    
    # TOP 25 BY RETURN
    print("\n🏆 TOP 25 BY TOTAL RETURN:", flush=True)
    by_ret = sorted(results, key=lambda x: x['ret'], reverse=True)[:25]
    for i, r in enumerate(by_ret, 1):
        p = r['params']
        print(f"\n{i:2}. Return: {r['ret']:+7.1f}% | {r['trades']:3} trades | Win: {r['wr']:3.0f}%", flush=True)
        print(f"    Strategy: {p['strat']:6} | RSI({p['rsi_p']}) OS:{p['rsi_os']} OB:{p['rsi_ob']}", flush=True)
        print(f"    MACD({p['macd']}) | SL:{p['sl']}% TP:{p['tp']}%", flush=True)
        if r['sample']:
            print(f"    Sample: {r['sample'][0]['entry'][:16]} → {r['sample'][0]['pnl_pct']:+.1f}%", flush=True)
    
    # TOP 15 BY WIN RATE (min 20 trades)
    print(f"\n{'='*60}", flush=True)
    print("🎯 TOP 15 BY WIN RATE (min 20 trades):", flush=True)
    by_wr = sorted([r for r in results if r['trades'] >= 20], key=lambda x: x['wr'], reverse=True)[:15]
    for i, r in enumerate(by_wr, 1):
        p = r['params']
        print(f"{i:2}. Win: {r['wr']:3.0f}% | Ret: {r['ret']:+6.1f}% | {r['trades']:3} trades | "
              f"{p['strat']:6} RSI({p['rsi_p']}) SL:{p['sl']}% TP:{p['tp']}%", flush=True)
    
    # STATS BY STRATEGY
    print(f"\n{'='*60}", flush=True)
    print("BY STRATEGY TYPE:", flush=True)
    for strat in strategies:
        sr = [r for r in results if r['params']['strat'] == strat]
        if sr:
            prof = len([r for r in sr if r['ret'] > 0]) / len(sr) * 100
            best = max(r['ret'] for r in sr)
            avg = np.mean([r['ret'] for r in sr])
            print(f"  {strat:6}: {len(sr):4} valid | Best: {best:+6.1f}% | Avg: {avg:+5.1f}% | {prof:4.0f}% profitable", flush=True)
    
    # SUMMARY
    print(f"\n{'='*60}", flush=True)
    print("SUMMARY:", flush=True)
    profitable = len([r for r in results if r['ret'] > 0])
    print(f"  Total valid: {len(results)}", flush=True)
    print(f"  Profitable: {profitable} ({profitable/len(results)*100:.0f}%)", flush=True)
    print(f"  Best: {max(r['ret'] for r in results):+.1f}%", flush=True)
    print(f"  Worst: {min(r['ret'] for r in results):+.1f}%", flush=True)
    print(f"  Average: {np.mean([r['ret'] for r in results]):+.1f}%", flush=True)
    
    # Save top 100
    top_100 = sorted(results, key=lambda x: x['ret'], reverse=True)[:100]
    with open(output_file, 'w') as f:
        json.dump(top_100, f, indent=2)
    print(f"\nTop 100 saved to: {output_file}", flush=True)
    
    print(f"\nFinished: {datetime.now()}", flush=True)

if __name__ == '__main__':
    main()
