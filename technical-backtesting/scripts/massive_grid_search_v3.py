#!/usr/bin/env python3
"""
Massive Grid Search v3 - 1000+ Strategy Combinations
Pre-fetches data then runs all parameter combinations
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

# Load env from script's parent directory
script_dir = os.path.dirname(os.path.abspath(__file__))
env_path = os.path.join(os.path.dirname(script_dir), '.env')
load_dotenv(env_path)

API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

# Symbols and timeframes to test
SYMBOLS = ['QQQ', 'SPY', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMD', 'META']
TIMEFRAMES = ['5m', '15m', '30m', '1h']

# Strategy parameters - designed for 1000+ combinations per symbol/timeframe
STRATEGY_PARAMS = {
    'rsi_period': [7, 9, 14, 21],
    'rsi_oversold': [20, 25, 30, 35],
    'rsi_overbought': [65, 70, 75, 80],
    'macd_fast': [8, 12],
    'macd_slow': [21, 26],
    'macd_signal': [7, 9],
    'stop_loss_pct': [0.5, 1.0, 1.5, 2.0, 2.5],
    'take_profit_pct': [1.0, 2.0, 3.0, 4.0, 5.0],
    'strategy_type': ['rsi_only', 'macd_only', 'rsi_macd_combo', 'rsi_macd_either']
}

def get_timeframe_obj(tf_str):
    if tf_str == '1m':
        return TimeFrame.Minute
    elif tf_str == '5m':
        return TimeFrame(5, TimeFrameUnit.Minute)
    elif tf_str == '15m':
        return TimeFrame(15, TimeFrameUnit.Minute)
    elif tf_str == '30m':
        return TimeFrame(30, TimeFrameUnit.Minute)
    elif tf_str == '1h':
        return TimeFrame.Hour
    else:
        return TimeFrame(5, TimeFrameUnit.Minute)

def fetch_data(client, symbol, timeframe_str, days=60):
    """Fetch historical data from Alpaca"""
    end = datetime.now()
    start = end - timedelta(days=days)
    
    try:
        request = StockBarsRequest(
            symbol_or_symbols=symbol,
            timeframe=get_timeframe_obj(timeframe_str),
            start=start,
            end=end,
            feed='iex'
        )
        
        bars = client.get_stock_bars(request)
        
        if not bars or symbol not in bars.data or len(bars.data[symbol]) == 0:
            return None
        
        data = []
        for bar in bars.data[symbol]:
            data.append({
                'timestamp': bar.timestamp,
                'open': float(bar.open),
                'high': float(bar.high),
                'low': float(bar.low),
                'close': float(bar.close),
                'volume': int(bar.volume)
            })
        
        df = pd.DataFrame(data)
        df.set_index('timestamp', inplace=True)
        df.sort_index(inplace=True)
        return df
    except Exception as e:
        print(f"Error fetching {symbol} {timeframe_str}: {e}")
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
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def run_backtest(df, params):
    """Run a single backtest with given parameters"""
    if df is None or len(df) < 100:
        return None
    
    df = df.copy()
    
    # Calculate indicators
    df['rsi'] = calculate_rsi(df['close'], params['rsi_period'])
    df['macd'], df['macd_signal_line'], df['macd_hist'] = calculate_macd(
        df['close'], params['macd_fast'], params['macd_slow'], params['macd_signal']
    )
    
    df.dropna(inplace=True)
    if len(df) < 50:
        return None
    
    # Generate signals based on strategy type
    strategy = params['strategy_type']
    
    rsi_buy = df['rsi'] < params['rsi_oversold']
    rsi_sell = df['rsi'] > params['rsi_overbought']
    macd_buy = (df['macd'] > df['macd_signal_line']) & (df['macd'].shift(1) <= df['macd_signal_line'].shift(1))
    macd_sell = (df['macd'] < df['macd_signal_line']) & (df['macd'].shift(1) >= df['macd_signal_line'].shift(1))
    
    if strategy == 'rsi_only':
        df['buy_signal'] = rsi_buy
        df['sell_signal'] = rsi_sell
    elif strategy == 'macd_only':
        df['buy_signal'] = macd_buy
        df['sell_signal'] = macd_sell
    elif strategy == 'rsi_macd_combo':
        df['buy_signal'] = rsi_buy & macd_buy
        df['sell_signal'] = rsi_sell | macd_sell
    else:  # rsi_macd_either
        df['buy_signal'] = rsi_buy | macd_buy
        df['sell_signal'] = rsi_sell | macd_sell
    
    # Simulate trading
    initial_capital = 10000
    capital = initial_capital
    position = 0
    entry_price = 0
    trades = []
    
    stop_loss = params['stop_loss_pct'] / 100
    take_profit = params['take_profit_pct'] / 100
    
    for idx in range(len(df)):
        row = df.iloc[idx]
        
        if position > 0:
            pnl_pct = (row['close'] - entry_price) / entry_price
            if pnl_pct <= -stop_loss or pnl_pct >= take_profit or row['sell_signal']:
                pnl = position * (row['close'] - entry_price)
                capital += position * row['close']
                trades.append({
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': 'stop_loss' if pnl_pct <= -stop_loss else ('take_profit' if pnl_pct >= take_profit else 'signal')
                })
                position = 0
        else:
            if row['buy_signal'] and capital > 0:
                position = capital / row['close']
                entry_price = row['close']
                capital = 0
    
    # Close any open position
    if position > 0:
        final_price = df.iloc[-1]['close']
        pnl = position * (final_price - entry_price)
        capital += position * final_price
        trades.append({
            'pnl': pnl,
            'pnl_pct': ((final_price - entry_price) / entry_price) * 100,
            'exit_reason': 'end_of_data'
        })
    
    if len(trades) == 0:
        return None
    
    # Calculate metrics
    total_return = ((capital - initial_capital) / initial_capital) * 100
    winning_trades = [t for t in trades if t['pnl'] > 0]
    losing_trades = [t for t in trades if t['pnl'] <= 0]
    
    win_rate = len(winning_trades) / len(trades) * 100 if trades else 0
    avg_win = np.mean([t['pnl_pct'] for t in winning_trades]) if winning_trades else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losing_trades]) if losing_trades else 0
    
    gross_profit = sum(t['pnl'] for t in winning_trades) if winning_trades else 0
    gross_loss = abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else 0.001
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit
    
    # Max drawdown
    equity_curve = [initial_capital]
    running_capital = initial_capital
    for t in trades:
        running_capital += t['pnl']
        equity_curve.append(running_capital)
    
    peak = equity_curve[0]
    max_dd = 0
    for eq in equity_curve:
        if eq > peak:
            peak = eq
        dd = (peak - eq) / peak * 100
        if dd > max_dd:
            max_dd = dd
    
    return {
        'total_return': round(total_return, 2),
        'num_trades': len(trades),
        'win_rate': round(win_rate, 1),
        'profit_factor': round(profit_factor, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'max_drawdown': round(max_dd, 2),
        'final_capital': round(capital, 2)
    }

def main():
    print("=" * 80, flush=True)
    print("MASSIVE GRID SEARCH - 1000+ STRATEGY COMBINATIONS", flush=True)
    print("=" * 80, flush=True)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    print(flush=True)
    
    # Initialize client
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    print("API client initialized", flush=True)
    
    # Generate strategy parameter combinations
    param_combos = list(itertools.product(
        STRATEGY_PARAMS['rsi_period'],
        STRATEGY_PARAMS['rsi_oversold'],
        STRATEGY_PARAMS['rsi_overbought'],
        STRATEGY_PARAMS['macd_fast'],
        STRATEGY_PARAMS['macd_slow'],
        STRATEGY_PARAMS['macd_signal'],
        STRATEGY_PARAMS['stop_loss_pct'],
        STRATEGY_PARAMS['take_profit_pct'],
        STRATEGY_PARAMS['strategy_type']
    ))
    
    # Filter invalid MACD combos
    param_combos = [c for c in param_combos if c[3] < c[4]]
    
    print(f"Strategy parameter combinations: {len(param_combos)}", flush=True)
    print(f"Symbols: {len(SYMBOLS)}", flush=True)
    print(f"Timeframes: {len(TIMEFRAMES)}", flush=True)
    print(f"Total combinations: {len(param_combos) * len(SYMBOLS) * len(TIMEFRAMES)}", flush=True)
    print(flush=True)
    
    # Pre-fetch all data
    print("Step 1: Fetching market data...", flush=True)
    data_cache = {}
    for symbol in SYMBOLS:
        for tf in TIMEFRAMES:
            key = f"{symbol}_{tf}"
            print(f"  Fetching {symbol} {tf}...", end=" ", flush=True)
            df = fetch_data(client, symbol, tf, days=60)
            if df is not None:
                data_cache[key] = df
                print(f"✓ ({len(df)} bars)", flush=True)
            else:
                print("✗ (no data)", flush=True)
    
    print(f"\nFetched data for {len(data_cache)} symbol/timeframe combinations", flush=True)
    print(flush=True)
    
    if len(data_cache) == 0:
        print("No data fetched! Exiting.", flush=True)
        return
    
    # Run all backtests
    print("Step 2: Running backtests...", flush=True)
    results = []
    total_tests = len(param_combos) * len(data_cache)
    tests_run = 0
    
    for key, df in data_cache.items():
        symbol, tf = key.split('_')
        
        for combo in param_combos:
            rsi_p, rsi_os, rsi_ob, macd_f, macd_s, macd_sig, sl, tp, strat = combo
            
            params = {
                'symbol': symbol,
                'timeframe': tf,
                'rsi_period': rsi_p,
                'rsi_oversold': rsi_os,
                'rsi_overbought': rsi_ob,
                'macd_fast': macd_f,
                'macd_slow': macd_s,
                'macd_signal': macd_sig,
                'stop_loss_pct': sl,
                'take_profit_pct': tp,
                'strategy_type': strat
            }
            
            result = run_backtest(df, params)
            if result:
                result['params'] = params
                results.append(result)
            
            tests_run += 1
        
        pct = tests_run / total_tests * 100
        valid_for_this = len([r for r in results if r['params']['symbol']==symbol and r['params']['timeframe']==tf])
        print(f"  {symbol} {tf}: {valid_for_this} valid strategies | Progress: {pct:.0f}%", flush=True)
    
    print(flush=True)
    print(f"Completed: {len(results)} strategies produced valid results", flush=True)
    print(flush=True)
    
    if not results:
        print("No valid results found!", flush=True)
        return
    
    # Sort and display results
    print("=" * 80, flush=True)
    print("TOP 25 STRATEGIES BY TOTAL RETURN", flush=True)
    print("=" * 80, flush=True)
    
    by_return = sorted(results, key=lambda x: x['total_return'], reverse=True)[:25]
    for i, r in enumerate(by_return, 1):
        p = r['params']
        print(f"\n{i}. {p['symbol']} {p['timeframe']} - {p['strategy_type']}", flush=True)
        print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']} | MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})", flush=True)
        print(f"   SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%", flush=True)
        print(f"   Return: {r['total_return']:+.1f}% | Trades: {r['num_trades']} | Win Rate: {r['win_rate']:.0f}% | PF: {r['profit_factor']} | Max DD: {r['max_drawdown']:.1f}%", flush=True)
    
    print(flush=True)
    print("=" * 80, flush=True)
    print("TOP 25 BY PROFIT FACTOR (min 10 trades)", flush=True)
    print("=" * 80, flush=True)
    
    by_pf = sorted([r for r in results if r['num_trades'] >= 10], 
                   key=lambda x: x['profit_factor'], reverse=True)[:25]
    for i, r in enumerate(by_pf, 1):
        p = r['params']
        print(f"\n{i}. {p['symbol']} {p['timeframe']} - {p['strategy_type']}", flush=True)
        print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']} | MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})", flush=True)
        print(f"   SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%", flush=True)
        print(f"   PF: {r['profit_factor']} | Return: {r['total_return']:+.1f}% | Trades: {r['num_trades']} | Win Rate: {r['win_rate']:.0f}% | Max DD: {r['max_drawdown']:.1f}%", flush=True)
    
    print(flush=True)
    print("=" * 80, flush=True)
    print("TOP 25 BY WIN RATE (min 10 trades)", flush=True)
    print("=" * 80, flush=True)
    
    by_wr = sorted([r for r in results if r['num_trades'] >= 10], 
                   key=lambda x: x['win_rate'], reverse=True)[:25]
    for i, r in enumerate(by_wr, 1):
        p = r['params']
        print(f"\n{i}. {p['symbol']} {p['timeframe']} - {p['strategy_type']}", flush=True)
        print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']} | MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})", flush=True)
        print(f"   SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%", flush=True)
        print(f"   Win Rate: {r['win_rate']:.0f}% | Return: {r['total_return']:+.1f}% | Trades: {r['num_trades']} | PF: {r['profit_factor']} | Max DD: {r['max_drawdown']:.1f}%", flush=True)
    
    # Composite score ranking
    print(flush=True)
    print("=" * 80, flush=True)
    print("TOP 25 RISK-ADJUSTED (Composite Score)", flush=True)
    print("=" * 80, flush=True)
    
    returns = [r['total_return'] for r in results]
    pfs = [r['profit_factor'] for r in results]
    wrs = [r['win_rate'] for r in results]
    dds = [r['max_drawdown'] for r in results]
    
    r_min, r_max = min(returns), max(returns)
    pf_min, pf_max = min(pfs), max(pfs)
    wr_min, wr_max = min(wrs), max(wrs)
    dd_min, dd_max = min(dds), max(dds)
    
    for r in results:
        r_norm = (r['total_return'] - r_min) / (r_max - r_min + 0.0001)
        pf_norm = (r['profit_factor'] - pf_min) / (pf_max - pf_min + 0.0001)
        wr_norm = (r['win_rate'] - wr_min) / (wr_max - wr_min + 0.0001)
        dd_norm = 1 - (r['max_drawdown'] - dd_min) / (dd_max - dd_min + 0.0001)
        r['composite_score'] = (r_norm * 0.35 + pf_norm * 0.25 + wr_norm * 0.2 + dd_norm * 0.2)
    
    by_composite = sorted([r for r in results if r['num_trades'] >= 5], 
                          key=lambda x: x['composite_score'], reverse=True)[:25]
    
    for i, r in enumerate(by_composite, 1):
        p = r['params']
        print(f"\n{i}. {p['symbol']} {p['timeframe']} - {p['strategy_type']}", flush=True)
        print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']} | MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})", flush=True)
        print(f"   SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%", flush=True)
        print(f"   Score: {r['composite_score']:.3f} | Return: {r['total_return']:+.1f}% | PF: {r['profit_factor']} | Win: {r['win_rate']:.0f}% | DD: {r['max_drawdown']:.1f}% | Trades: {r['num_trades']}", flush=True)
    
    # Summary
    print(flush=True)
    print("=" * 80, flush=True)
    print("SUMMARY STATISTICS", flush=True)
    print("=" * 80, flush=True)
    print(f"Total strategies tested: {len(results)}", flush=True)
    profitable = len([r for r in results if r['total_return'] > 0])
    print(f"Profitable strategies: {profitable} ({profitable/len(results)*100:.1f}%)", flush=True)
    print(f"Losing strategies: {len(results) - profitable} ({(len(results)-profitable)/len(results)*100:.1f}%)", flush=True)
    print(f"Average return: {np.mean([r['total_return'] for r in results]):.2f}%", flush=True)
    print(f"Best return: {max([r['total_return'] for r in results]):.2f}%", flush=True)
    print(f"Worst return: {min([r['total_return'] for r in results]):.2f}%", flush=True)
    print(f"Average win rate: {np.mean([r['win_rate'] for r in results]):.1f}%", flush=True)
    print(f"Average profit factor: {np.mean([r['profit_factor'] for r in results]):.2f}", flush=True)
    
    # Symbol breakdown
    print(flush=True)
    print("BY SYMBOL:", flush=True)
    for symbol in SYMBOLS:
        sym_results = [r for r in results if r['params']['symbol'] == symbol]
        if sym_results:
            avg_ret = np.mean([r['total_return'] for r in sym_results])
            best_ret = max([r['total_return'] for r in sym_results])
            print(f"  {symbol}: {len(sym_results)} strategies | Avg: {avg_ret:+.1f}% | Best: {best_ret:+.1f}%", flush=True)
    
    # Timeframe breakdown
    print(flush=True)
    print("BY TIMEFRAME:", flush=True)
    for tf in TIMEFRAMES:
        tf_results = [r for r in results if r['params']['timeframe'] == tf]
        if tf_results:
            avg_ret = np.mean([r['total_return'] for r in tf_results])
            best_ret = max([r['total_return'] for r in tf_results])
            print(f"  {tf}: {len(tf_results)} strategies | Avg: {avg_ret:+.1f}% | Best: {best_ret:+.1f}%", flush=True)
    
    # Strategy type breakdown
    print(flush=True)
    print("BY STRATEGY TYPE:", flush=True)
    for strat in STRATEGY_PARAMS['strategy_type']:
        strat_results = [r for r in results if r['params']['strategy_type'] == strat]
        if strat_results:
            avg_ret = np.mean([r['total_return'] for r in strat_results])
            best_ret = max([r['total_return'] for r in strat_results])
            prof_pct = len([r for r in strat_results if r['total_return'] > 0]) / len(strat_results) * 100
            print(f"  {strat}: {len(strat_results)} strategies | Avg: {avg_ret:+.1f}% | Best: {best_ret:+.1f}% | {prof_pct:.0f}% profitable", flush=True)
    
    # Save results
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grid_search_results.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull results saved to: {output_file}", flush=True)
    
    print(flush=True)
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

if __name__ == '__main__':
    main()
