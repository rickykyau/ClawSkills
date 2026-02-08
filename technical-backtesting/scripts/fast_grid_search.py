#!/usr/bin/env python3
"""
Fast Grid Search - Optimized for speed, still 1000+ strategies
"""

import os
import sys
import json
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

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

# Reduced config for speed
SYMBOLS = ['QQQ', 'SPY', 'NVDA', 'TSLA']
TIMEFRAMES = ['15m', '1h']

def fetch_all_data(client):
    """Pre-fetch all data upfront"""
    cache = {}
    end = datetime.now()
    start = end - timedelta(days=60)
    
    for sym in SYMBOLS:
        for tf in TIMEFRAMES:
            key = f"{sym}_{tf}"
            print(f"  Fetching {sym} {tf}...", end=" ", flush=True)
            try:
                tf_obj = TimeFrame(15, TimeFrameUnit.Minute) if tf == '15m' else TimeFrame.Hour
                req = StockBarsRequest(symbol_or_symbols=sym, timeframe=tf_obj, start=start, end=end, feed='iex')
                bars = client.get_stock_bars(req)
                if bars and sym in bars.data:
                    df = pd.DataFrame([{
                        'timestamp': b.timestamp, 'close': float(b.close)
                    } for b in bars.data[sym]]).set_index('timestamp').sort_index()
                    cache[key] = df
                    print(f"✓ {len(df)} bars", flush=True)
                else:
                    print("✗", flush=True)
            except Exception as e:
                print(f"✗ {e}", flush=True)
    return cache

def backtest(df, rsi_p, rsi_os, rsi_ob, macd_f, macd_s, macd_sig, sl, tp, strat):
    """Ultra-fast backtest using vectorized operations"""
    if df is None or len(df) < 100:
        return None
    
    close = df['close'].values
    n = len(close)
    
    # Calculate RSI
    delta = np.diff(close, prepend=close[0])
    gain = np.where(delta > 0, delta, 0)
    loss = np.where(delta < 0, -delta, 0)
    
    avg_gain = np.convolve(gain, np.ones(rsi_p)/rsi_p, mode='valid')
    avg_loss = np.convolve(loss, np.ones(rsi_p)/rsi_p, mode='valid')
    
    with np.errstate(divide='ignore', invalid='ignore'):
        rs = avg_gain / np.where(avg_loss == 0, 1, avg_loss)
        rsi = 100 - (100 / (1 + rs))
    
    # Pad RSI to match length
    pad = n - len(rsi)
    rsi = np.concatenate([np.full(pad, 50), rsi])
    
    # Calculate MACD
    ema_fast = pd.Series(close).ewm(span=macd_f, adjust=False).mean().values
    ema_slow = pd.Series(close).ewm(span=macd_s, adjust=False).mean().values
    macd = ema_fast - ema_slow
    macd_signal = pd.Series(macd).ewm(span=macd_sig, adjust=False).mean().values
    
    # Generate signals
    rsi_buy = rsi < rsi_os
    rsi_sell = rsi > rsi_ob
    macd_buy = (macd > macd_signal) & (np.roll(macd, 1) <= np.roll(macd_signal, 1))
    macd_sell = (macd < macd_signal) & (np.roll(macd, 1) >= np.roll(macd_signal, 1))
    
    if strat == 'rsi':
        buy, sell = rsi_buy, rsi_sell
    elif strat == 'macd':
        buy, sell = macd_buy, macd_sell
    else:
        buy = rsi_buy & macd_buy
        sell = rsi_sell | macd_sell
    
    # Simulate
    capital, pos, entry = 10000.0, 0.0, 0.0
    trades = []
    sl_pct, tp_pct = sl / 100, tp / 100
    
    for i in range(50, n):  # Skip warmup
        if pos > 0:
            pnl_pct = (close[i] - entry) / entry
            if pnl_pct <= -sl_pct or pnl_pct >= tp_pct or sell[i]:
                capital += pos * close[i]
                trades.append(pos * (close[i] - entry))
                pos = 0
        elif buy[i] and capital > 0:
            pos, entry, capital = capital / close[i], close[i], 0
    
    if pos > 0:
        capital += pos * close[-1]
        trades.append(pos * (close[-1] - entry))
    
    if not trades:
        return None
    
    total_ret = (capital - 10000) / 100
    wins = sum(1 for t in trades if t > 0)
    win_rate = wins / len(trades) * 100
    gross_win = sum(t for t in trades if t > 0)
    gross_loss = abs(sum(t for t in trades if t < 0)) or 0.01
    pf = gross_win / gross_loss
    
    return {
        'ret': round(total_ret, 2),
        'trades': len(trades),
        'wr': round(win_rate, 0),
        'pf': round(pf, 2)
    }

def main():
    print("=" * 60, flush=True)
    print("FAST GRID SEARCH - 1000+ STRATEGIES", flush=True)
    print("=" * 60, flush=True)
    
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    print("\nFetching data...", flush=True)
    data = fetch_all_data(client)
    print(f"\nGot {len(data)} datasets", flush=True)
    
    if not data:
        print("No data!")
        return
    
    # Parameter ranges
    rsi_periods = [7, 14, 21]
    rsi_os = [20, 25, 30]
    rsi_ob = [70, 75, 80]
    macd_fast = [8, 12]
    macd_slow = [21, 26]
    macd_sig = [9]
    stop_loss = [1.0, 1.5, 2.0]
    take_profit = [2.0, 3.0, 5.0]
    strategies = ['rsi', 'macd', 'combo']
    
    results = []
    total = 0
    
    print("\nRunning backtests...", flush=True)
    
    for key, df in data.items():
        sym, tf = key.split('_')
        chunk_results = []
        
        for rp in rsi_periods:
            for ros in rsi_os:
                for rob in rsi_ob:
                    for mf in macd_fast:
                        for ms in macd_slow:
                            if mf >= ms:
                                continue
                            for msig in macd_sig:
                                for sl in stop_loss:
                                    for tp in take_profit:
                                        for strat in strategies:
                                            total += 1
                                            r = backtest(df, rp, ros, rob, mf, ms, msig, sl, tp, strat)
                                            if r:
                                                r['sym'] = sym
                                                r['tf'] = tf
                                                r['rsi_p'] = rp
                                                r['rsi_os'] = ros
                                                r['rsi_ob'] = rob
                                                r['macd'] = f"{mf}/{ms}/{msig}"
                                                r['sl'] = sl
                                                r['tp'] = tp
                                                r['strat'] = strat
                                                chunk_results.append(r)
        
        results.extend(chunk_results)
        if chunk_results:
            best = max(chunk_results, key=lambda x: x['ret'])
            print(f"  {sym} {tf}: {len(chunk_results)} valid | Best: {best['ret']:+.1f}%", flush=True)
    
    print(f"\nTested {total} combinations, {len(results)} valid", flush=True)
    
    if not results:
        return
    
    # RESULTS
    print("\n" + "=" * 60, flush=True)
    print("🏆 TOP 15 BY RETURN", flush=True)
    print("=" * 60, flush=True)
    
    by_ret = sorted(results, key=lambda x: x['ret'], reverse=True)[:15]
    for i, r in enumerate(by_ret, 1):
        print(f"{i:2}. {r['sym']:4} {r['tf']:3} {r['strat']:5} | Ret: {r['ret']:+6.1f}% | "
              f"Trades: {r['trades']:2} | Win: {r['wr']:3.0f}% | PF: {r['pf']:5.2f}", flush=True)
        print(f"    RSI({r['rsi_p']}) OS:{r['rsi_os']} OB:{r['rsi_ob']} | MACD({r['macd']}) | SL:{r['sl']}% TP:{r['tp']}%", flush=True)
    
    print("\n" + "=" * 60, flush=True)
    print("📊 TOP 15 BY PROFIT FACTOR (5+ trades)", flush=True)
    print("=" * 60, flush=True)
    
    by_pf = sorted([r for r in results if r['trades'] >= 5], key=lambda x: x['pf'], reverse=True)[:15]
    for i, r in enumerate(by_pf, 1):
        print(f"{i:2}. {r['sym']:4} {r['tf']:3} {r['strat']:5} | PF: {r['pf']:5.2f} | "
              f"Ret: {r['ret']:+6.1f}% | Trades: {r['trades']:2} | Win: {r['wr']:3.0f}%", flush=True)
    
    print("\n" + "=" * 60, flush=True)
    print("🎯 TOP 15 BY WIN RATE (5+ trades)", flush=True)
    print("=" * 60, flush=True)
    
    by_wr = sorted([r for r in results if r['trades'] >= 5], key=lambda x: x['wr'], reverse=True)[:15]
    for i, r in enumerate(by_wr, 1):
        print(f"{i:2}. {r['sym']:4} {r['tf']:3} {r['strat']:5} | Win: {r['wr']:3.0f}% | "
              f"Ret: {r['ret']:+6.1f}% | PF: {r['pf']:5.2f} | Trades: {r['trades']:2}", flush=True)
    
    # Summary
    print("\n" + "=" * 60, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 60, flush=True)
    
    profitable = len([r for r in results if r['ret'] > 0])
    print(f"Total: {len(results)} | Profitable: {profitable} ({profitable/len(results)*100:.0f}%)", flush=True)
    print(f"Avg return: {np.mean([r['ret'] for r in results]):.2f}%", flush=True)
    print(f"Best: {max(r['ret'] for r in results):.2f}% | Worst: {min(r['ret'] for r in results):.2f}%", flush=True)
    
    print("\nBY SYMBOL:", flush=True)
    for sym in SYMBOLS:
        sr = [r for r in results if r['sym'] == sym]
        if sr:
            print(f"  {sym}: Best {max(r['ret'] for r in sr):+.1f}% | Avg {np.mean([r['ret'] for r in sr]):+.1f}%", flush=True)
    
    print("\nBY STRATEGY:", flush=True)
    for strat in strategies:
        sr = [r for r in results if r['strat'] == strat]
        if sr:
            prof = len([r for r in sr if r['ret'] > 0]) / len(sr) * 100
            print(f"  {strat}: Best {max(r['ret'] for r in sr):+.1f}% | {prof:.0f}% profitable", flush=True)
    
    # Save
    out = os.path.join(script_dir, 'grid_results.json')
    with open(out, 'w') as f:
        json.dump(results, f, indent=2)
    print(f"\nSaved to: {out}", flush=True)

if __name__ == '__main__':
    main()
