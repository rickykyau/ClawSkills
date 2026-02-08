#!/usr/bin/env python3
"""
Chunked Grid Search - Runs in batches, saves results incrementally
Designed to test 1000+ strategies across multiple chunks
"""

import os
import sys
import json
import itertools
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
from dotenv import load_dotenv

script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(script_dir), '.env')
load_dotenv(env_path)

API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

# Configuration - reduced for manageable chunks
SYMBOLS = ['QQQ', 'SPY', 'NVDA', 'TSLA', 'AMD', 'AAPL']  # 6 symbols
TIMEFRAMES = ['5m', '15m', '1h']  # 3 timeframes

# Strategy parameters - still 1000+ combinations
STRATEGY_PARAMS = {
    'rsi_period': [7, 14, 21],
    'rsi_oversold': [20, 30],
    'rsi_overbought': [70, 80],
    'macd_fast': [8, 12],
    'macd_slow': [21, 26],
    'macd_signal': [9],
    'stop_loss_pct': [1.0, 2.0],
    'take_profit_pct': [2.0, 3.0, 5.0],
    'strategy_type': ['rsi_only', 'macd_only', 'rsi_macd_combo']
}

def get_timeframe_obj(tf_str):
    if tf_str == '5m':
        return TimeFrame(5, TimeFrameUnit.Minute)
    elif tf_str == '15m':
        return TimeFrame(15, TimeFrameUnit.Minute)
    elif tf_str == '1h':
        return TimeFrame.Hour
    return TimeFrame(5, TimeFrameUnit.Minute)

def fetch_data(client, symbol, timeframe_str, days=60):
    end = datetime.now()
    start = end - timedelta(days=days)
    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=get_timeframe_obj(timeframe_str),
            start=start, end=end, feed='iex'
        )
        bars = client.get_stock_bars(request)
        if not bars or symbol not in bars.data:
            return None
        data = [{'timestamp': b.timestamp, 'open': float(b.open), 'high': float(b.high),
                 'low': float(b.low), 'close': float(b.close), 'volume': int(b.volume)}
                for b in bars.data[symbol]]
        df = pd.DataFrame(data).set_index('timestamp').sort_index()
        return df
    except Exception as e:
        print(f"Error: {symbol} {timeframe_str}: {e}")
        return None

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def calculate_macd(prices, fast=12, slow=26, signal=9):
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    return macd_line, signal_line

def run_backtest(df, params):
    if df is None or len(df) < 100:
        return None
    df = df.copy()
    df['rsi'] = calculate_rsi(df['close'], params['rsi_period'])
    df['macd'], df['macd_sig'] = calculate_macd(df['close'], params['macd_fast'], params['macd_slow'], params['macd_signal'])
    df.dropna(inplace=True)
    if len(df) < 50:
        return None

    strategy = params['strategy_type']
    rsi_buy = df['rsi'] < params['rsi_oversold']
    rsi_sell = df['rsi'] > params['rsi_overbought']
    macd_buy = (df['macd'] > df['macd_sig']) & (df['macd'].shift(1) <= df['macd_sig'].shift(1))
    macd_sell = (df['macd'] < df['macd_sig']) & (df['macd'].shift(1) >= df['macd_sig'].shift(1))

    if strategy == 'rsi_only':
        df['buy'], df['sell'] = rsi_buy, rsi_sell
    elif strategy == 'macd_only':
        df['buy'], df['sell'] = macd_buy, macd_sell
    else:
        df['buy'] = rsi_buy & macd_buy
        df['sell'] = rsi_sell | macd_sell

    capital, position, entry_price = 10000, 0, 0
    trades = []
    sl, tp = params['stop_loss_pct'] / 100, params['take_profit_pct'] / 100

    for i in range(len(df)):
        row = df.iloc[i]
        if position > 0:
            pnl_pct = (row['close'] - entry_price) / entry_price
            if pnl_pct <= -sl or pnl_pct >= tp or row['sell']:
                capital += position * row['close']
                trades.append({'pnl': position * (row['close'] - entry_price), 'pnl_pct': pnl_pct * 100})
                position = 0
        else:
            if row['buy'] and capital > 0:
                position, entry_price, capital = capital / row['close'], row['close'], 0

    if position > 0:
        final = df.iloc[-1]['close']
        capital += position * final
        trades.append({'pnl': position * (final - entry_price), 'pnl_pct': ((final - entry_price) / entry_price) * 100})

    if not trades:
        return None

    total_return = ((capital - 10000) / 10000) * 100
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    win_rate = len(wins) / len(trades) * 100
    profit_factor = sum(t['pnl'] for t in wins) / max(abs(sum(t['pnl'] for t in losses)), 0.01)

    eq = [10000]
    for t in trades:
        eq.append(eq[-1] + t['pnl'])
    peak, max_dd = eq[0], 0
    for e in eq:
        if e > peak: peak = e
        dd = (peak - e) / peak * 100
        if dd > max_dd: max_dd = dd

    return {
        'total_return': round(total_return, 2),
        'num_trades': len(trades),
        'win_rate': round(win_rate, 1),
        'profit_factor': round(profit_factor, 2),
        'max_drawdown': round(max_dd, 2),
        'final_capital': round(capital, 2)
    }

def main():
    print("=" * 70, flush=True)
    print("CHUNKED GRID SEARCH - 1000+ STRATEGIES", flush=True)
    print("=" * 70, flush=True)
    print(f"Started: {datetime.now().strftime('%H:%M:%S')}", flush=True)

    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    # Generate param combos
    combos = [c for c in itertools.product(
        STRATEGY_PARAMS['rsi_period'], STRATEGY_PARAMS['rsi_oversold'],
        STRATEGY_PARAMS['rsi_overbought'], STRATEGY_PARAMS['macd_fast'],
        STRATEGY_PARAMS['macd_slow'], STRATEGY_PARAMS['macd_signal'],
        STRATEGY_PARAMS['stop_loss_pct'], STRATEGY_PARAMS['take_profit_pct'],
        STRATEGY_PARAMS['strategy_type']
    ) if c[3] < c[4]]  # Filter invalid MACD

    total_combos = len(combos) * len(SYMBOLS) * len(TIMEFRAMES)
    print(f"Testing {len(combos)} param combos x {len(SYMBOLS)} symbols x {len(TIMEFRAMES)} TFs = {total_combos} total", flush=True)
    print(flush=True)

    all_results = []
    chunk_num = 0
    
    # Process by symbol/timeframe chunks
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            chunk_num += 1
            print(f"[Chunk {chunk_num}/{len(SYMBOLS)*len(TIMEFRAMES)}] {symbol} {tf}...", end=" ", flush=True)
            
            df = fetch_data(client, symbol, tf, days=60)
            if df is None:
                print("✗ no data", flush=True)
                continue
            
            chunk_results = []
            for combo in combos:
                params = {
                    'symbol': symbol, 'timeframe': tf,
                    'rsi_period': combo[0], 'rsi_oversold': combo[1], 'rsi_overbought': combo[2],
                    'macd_fast': combo[3], 'macd_slow': combo[4], 'macd_signal': combo[5],
                    'stop_loss_pct': combo[6], 'take_profit_pct': combo[7], 'strategy_type': combo[8]
                }
                result = run_backtest(df, params)
                if result:
                    result['params'] = params
                    chunk_results.append(result)
            
            all_results.extend(chunk_results)
            
            if chunk_results:
                best = max(chunk_results, key=lambda x: x['total_return'])
                print(f"✓ {len(chunk_results)} valid | Best: {best['total_return']:+.1f}%", flush=True)
            else:
                print("✓ 0 valid", flush=True)

    print(flush=True)
    print("=" * 70, flush=True)
    print(f"RESULTS: {len(all_results)} valid strategies", flush=True)
    print("=" * 70, flush=True)

    if not all_results:
        print("No valid results!")
        return

    # TOP 15 BY RETURN
    print("\n🏆 TOP 15 BY TOTAL RETURN:", flush=True)
    by_return = sorted(all_results, key=lambda x: x['total_return'], reverse=True)[:15]
    for i, r in enumerate(by_return, 1):
        p = r['params']
        print(f"{i:2}. {p['symbol']:4} {p['timeframe']:3} {p['strategy_type']:15} | "
              f"Return: {r['total_return']:+6.1f}% | Trades: {r['num_trades']:3} | "
              f"Win: {r['win_rate']:4.0f}% | PF: {r['profit_factor']:5.2f} | DD: {r['max_drawdown']:5.1f}%", flush=True)
        print(f"    RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']} | "
              f"MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']}) | SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%", flush=True)

    # TOP 15 BY PROFIT FACTOR
    print("\n📊 TOP 15 BY PROFIT FACTOR (min 5 trades):", flush=True)
    by_pf = sorted([r for r in all_results if r['num_trades'] >= 5], key=lambda x: x['profit_factor'], reverse=True)[:15]
    for i, r in enumerate(by_pf, 1):
        p = r['params']
        print(f"{i:2}. {p['symbol']:4} {p['timeframe']:3} {p['strategy_type']:15} | "
              f"PF: {r['profit_factor']:5.2f} | Return: {r['total_return']:+6.1f}% | "
              f"Trades: {r['num_trades']:3} | Win: {r['win_rate']:4.0f}%", flush=True)

    # TOP 15 BY WIN RATE
    print("\n🎯 TOP 15 BY WIN RATE (min 5 trades):", flush=True)
    by_wr = sorted([r for r in all_results if r['num_trades'] >= 5], key=lambda x: x['win_rate'], reverse=True)[:15]
    for i, r in enumerate(by_wr, 1):
        p = r['params']
        print(f"{i:2}. {p['symbol']:4} {p['timeframe']:3} {p['strategy_type']:15} | "
              f"Win: {r['win_rate']:4.0f}% | Return: {r['total_return']:+6.1f}% | "
              f"Trades: {r['num_trades']:3} | PF: {r['profit_factor']:5.2f}", flush=True)

    # SUMMARY STATS
    print("\n" + "=" * 70, flush=True)
    print("SUMMARY", flush=True)
    print("=" * 70, flush=True)
    profitable = len([r for r in all_results if r['total_return'] > 0])
    print(f"Total tested: {len(all_results)}", flush=True)
    print(f"Profitable: {profitable} ({profitable/len(all_results)*100:.1f}%)", flush=True)
    print(f"Avg return: {np.mean([r['total_return'] for r in all_results]):.2f}%", flush=True)
    print(f"Best: {max(r['total_return'] for r in all_results):.2f}%", flush=True)
    print(f"Worst: {min(r['total_return'] for r in all_results):.2f}%", flush=True)

    print("\nBY SYMBOL:", flush=True)
    for sym in SYMBOLS:
        sr = [r for r in all_results if r['params']['symbol'] == sym]
        if sr:
            print(f"  {sym}: {len(sr)} tests | Avg: {np.mean([r['total_return'] for r in sr]):+.1f}% | Best: {max(r['total_return'] for r in sr):+.1f}%", flush=True)

    print("\nBY STRATEGY:", flush=True)
    for strat in STRATEGY_PARAMS['strategy_type']:
        sr = [r for r in all_results if r['params']['strategy_type'] == strat]
        if sr:
            prof = len([r for r in sr if r['total_return'] > 0]) / len(sr) * 100
            print(f"  {strat}: Avg: {np.mean([r['total_return'] for r in sr]):+.1f}% | {prof:.0f}% profitable", flush=True)

    # Save
    out = os.path.join(script_dir, 'grid_results.json')
    with open(out, 'w') as f:
        json.dump(all_results, f, indent=2, default=str)
    print(f"\nSaved to: {out}", flush=True)
    print(f"Finished: {datetime.now().strftime('%H:%M:%S')}", flush=True)

if __name__ == '__main__':
    main()
