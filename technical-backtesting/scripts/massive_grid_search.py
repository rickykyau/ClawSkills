#!/usr/bin/env python3
"""
Massive Grid Search - 1000+ Strategy Combinations
Tests across symbols, timeframes, and many indicator settings
"""

import os
import sys
import json
import itertools
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor, as_completed
import warnings
warnings.filterwarnings('ignore')

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

# Load credentials
from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

API_KEY = os.getenv('ALPACA_API_KEY')
SECRET_KEY = os.getenv('ALPACA_SECRET_KEY')

# Parameter grid - designed for 1000+ combinations
PARAM_GRID = {
    'symbols': ['QQQ', 'SPY', 'AAPL', 'MSFT', 'NVDA', 'TSLA', 'AMD', 'META'],
    'timeframes': ['5m', '15m', '30m', '1h'],
    'rsi_period': [7, 9, 14, 21],
    'rsi_oversold': [20, 25, 30, 35],
    'rsi_overbought': [65, 70, 75, 80],
    'macd_fast': [8, 12, 16],
    'macd_slow': [21, 26, 30],
    'macd_signal': [7, 9, 11],
    'stop_loss_pct': [0.5, 1.0, 1.5, 2.0],
    'take_profit_pct': [1.0, 2.0, 3.0, 4.0, 5.0],
    'strategy_type': ['rsi_only', 'macd_only', 'rsi_macd_combo', 'rsi_macd_either']
}

def get_timeframe_obj(tf_str):
    mapping = {
        '1m': TimeFrame.Minute,
        '5m': TimeFrame(5, 'Min'),
        '15m': TimeFrame(15, 'Min'),
        '30m': TimeFrame(30, 'Min'),
        '1h': TimeFrame.Hour,
        '4h': TimeFrame(4, 'Hour'),
        '1d': TimeFrame.Day
    }
    return mapping.get(tf_str, TimeFrame(5, 'Min'))

def fetch_data(symbol, timeframe_str, days=60):
    """Fetch historical data from Alpaca"""
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    end = datetime.now()
    start = end - timedelta(days=days)
    
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

def calculate_rsi(prices, period=14):
    delta = prices.diff()
    gain = delta.where(delta > 0, 0).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
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
    df['macd'], df['macd_signal'], df['macd_hist'] = calculate_macd(
        df['close'], params['macd_fast'], params['macd_slow'], params['macd_signal']
    )
    
    df.dropna(inplace=True)
    if len(df) < 50:
        return None
    
    # Generate signals based on strategy type
    strategy = params['strategy_type']
    
    rsi_buy = df['rsi'] < params['rsi_oversold']
    rsi_sell = df['rsi'] > params['rsi_overbought']
    macd_buy = (df['macd'] > df['macd_signal']) & (df['macd'].shift(1) <= df['macd_signal'].shift(1))
    macd_sell = (df['macd'] < df['macd_signal']) & (df['macd'].shift(1) >= df['macd_signal'].shift(1))
    
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
    
    for idx, row in df.iterrows():
        if position > 0:
            # Check stop loss / take profit
            pnl_pct = (row['close'] - entry_price) / entry_price
            if pnl_pct <= -stop_loss or pnl_pct >= take_profit or row['sell_signal']:
                # Exit position
                pnl = position * (row['close'] - entry_price)
                capital += position * row['close']
                trades.append({
                    'entry_price': entry_price,
                    'exit_price': row['close'],
                    'pnl': pnl,
                    'pnl_pct': pnl_pct * 100,
                    'exit_reason': 'stop_loss' if pnl_pct <= -stop_loss else ('take_profit' if pnl_pct >= take_profit else 'signal')
                })
                position = 0
        else:
            # Look for entry
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
            'entry_price': entry_price,
            'exit_price': final_price,
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
    
    # Calculate profit factor
    gross_profit = sum(t['pnl'] for t in winning_trades) if winning_trades else 0
    gross_loss = abs(sum(t['pnl'] for t in losing_trades)) if losing_trades else 1
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else gross_profit
    
    # Calculate max drawdown
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
        'params': params,
        'total_return': round(total_return, 2),
        'num_trades': len(trades),
        'win_rate': round(win_rate, 1),
        'profit_factor': round(profit_factor, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'max_drawdown': round(max_dd, 2),
        'final_capital': round(capital, 2)
    }

def test_single_combo(combo):
    """Test a single parameter combination"""
    symbol, tf, rsi_p, rsi_os, rsi_ob, macd_f, macd_s, macd_sig, sl, tp, strat = combo
    
    # Skip invalid MACD combos
    if macd_f >= macd_s:
        return None
    
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
    
    try:
        df = fetch_data(symbol, tf, days=60)
        result = run_backtest(df, params)
        if result:
            return result
    except Exception as e:
        pass
    
    return None

def main():
    print("=" * 80)
    print("MASSIVE GRID SEARCH - 1000+ STRATEGY COMBINATIONS")
    print("=" * 80)
    print(f"Started at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()
    
    # Generate all combinations
    all_combos = list(itertools.product(
        PARAM_GRID['symbols'],
        PARAM_GRID['timeframes'],
        PARAM_GRID['rsi_period'],
        PARAM_GRID['rsi_oversold'],
        PARAM_GRID['rsi_overbought'],
        PARAM_GRID['macd_fast'],
        PARAM_GRID['macd_slow'],
        PARAM_GRID['macd_signal'],
        PARAM_GRID['stop_loss_pct'],
        PARAM_GRID['take_profit_pct'],
        PARAM_GRID['strategy_type']
    ))
    
    # Filter out invalid MACD combos (fast >= slow)
    valid_combos = [c for c in all_combos if c[5] < c[6]]
    
    print(f"Total parameter combinations: {len(all_combos)}")
    print(f"Valid combinations (after filtering): {len(valid_combos)}")
    print()
    
    # Sample if too many (to keep runtime reasonable while still testing 1000+)
    if len(valid_combos) > 2000:
        np.random.seed(42)
        indices = np.random.choice(len(valid_combos), 2000, replace=False)
        valid_combos = [valid_combos[i] for i in indices]
        print(f"Sampled {len(valid_combos)} combinations for testing")
    
    print("Testing strategies... (this may take several minutes)")
    print()
    
    results = []
    batch_size = 50
    total_batches = (len(valid_combos) + batch_size - 1) // batch_size
    
    for batch_num in range(total_batches):
        start_idx = batch_num * batch_size
        end_idx = min(start_idx + batch_size, len(valid_combos))
        batch = valid_combos[start_idx:end_idx]
        
        for combo in batch:
            result = test_single_combo(combo)
            if result:
                results.append(result)
        
        if (batch_num + 1) % 10 == 0 or batch_num == total_batches - 1:
            pct = (batch_num + 1) / total_batches * 100
            print(f"Progress: {pct:.0f}% ({len(results)} valid results so far)")
    
    print()
    print(f"Completed: {len(results)} strategies produced valid results")
    print()
    
    if not results:
        print("No valid results found!")
        return
    
    # Sort by different metrics
    print("=" * 80)
    print("TOP 20 STRATEGIES BY TOTAL RETURN")
    print("=" * 80)
    
    by_return = sorted(results, key=lambda x: x['total_return'], reverse=True)[:20]
    for i, r in enumerate(by_return, 1):
        p = r['params']
        print(f"\n{i}. {p['symbol']} {p['timeframe']} - {p['strategy_type']}")
        print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']}")
        print(f"   MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})")
        print(f"   SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%")
        print(f"   Return: {r['total_return']:+.1f}% | Trades: {r['num_trades']} | Win Rate: {r['win_rate']:.0f}%")
        print(f"   Profit Factor: {r['profit_factor']} | Max DD: {r['max_drawdown']:.1f}%")
    
    print()
    print("=" * 80)
    print("TOP 20 STRATEGIES BY PROFIT FACTOR (min 10 trades)")
    print("=" * 80)
    
    by_pf = sorted([r for r in results if r['num_trades'] >= 10], 
                   key=lambda x: x['profit_factor'], reverse=True)[:20]
    for i, r in enumerate(by_pf, 1):
        p = r['params']
        print(f"\n{i}. {p['symbol']} {p['timeframe']} - {p['strategy_type']}")
        print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']}")
        print(f"   MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})")
        print(f"   SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%")
        print(f"   Profit Factor: {r['profit_factor']} | Return: {r['total_return']:+.1f}%")
        print(f"   Trades: {r['num_trades']} | Win Rate: {r['win_rate']:.0f}% | Max DD: {r['max_drawdown']:.1f}%")
    
    print()
    print("=" * 80)
    print("TOP 20 STRATEGIES BY WIN RATE (min 10 trades)")
    print("=" * 80)
    
    by_wr = sorted([r for r in results if r['num_trades'] >= 10], 
                   key=lambda x: x['win_rate'], reverse=True)[:20]
    for i, r in enumerate(by_wr, 1):
        p = r['params']
        print(f"\n{i}. {p['symbol']} {p['timeframe']} - {p['strategy_type']}")
        print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']}")
        print(f"   MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})")
        print(f"   SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%")
        print(f"   Win Rate: {r['win_rate']:.0f}% | Return: {r['total_return']:+.1f}%")
        print(f"   Trades: {r['num_trades']} | Profit Factor: {r['profit_factor']} | Max DD: {r['max_drawdown']:.1f}%")
    
    print()
    print("=" * 80)
    print("BEST RISK-ADJUSTED (High Return + Low Drawdown + High Win Rate)")
    print("=" * 80)
    
    # Composite score: normalize and weight
    if results:
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
            dd_norm = 1 - (r['max_drawdown'] - dd_min) / (dd_max - dd_min + 0.0001)  # Lower DD is better
            
            # Composite score with weights
            r['composite_score'] = (r_norm * 0.35 + pf_norm * 0.25 + wr_norm * 0.2 + dd_norm * 0.2)
        
        by_composite = sorted([r for r in results if r['num_trades'] >= 5], 
                              key=lambda x: x['composite_score'], reverse=True)[:20]
        
        for i, r in enumerate(by_composite, 1):
            p = r['params']
            print(f"\n{i}. {p['symbol']} {p['timeframe']} - {p['strategy_type']}")
            print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']}")
            print(f"   MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})")
            print(f"   SL:{p['stop_loss_pct']}% TP:{p['take_profit_pct']}%")
            print(f"   Score: {r['composite_score']:.3f} | Return: {r['total_return']:+.1f}% | PF: {r['profit_factor']}")
            print(f"   Win Rate: {r['win_rate']:.0f}% | Max DD: {r['max_drawdown']:.1f}% | Trades: {r['num_trades']}")
    
    # Summary statistics
    print()
    print("=" * 80)
    print("SUMMARY STATISTICS")
    print("=" * 80)
    print(f"Total strategies tested: {len(results)}")
    print(f"Profitable strategies: {len([r for r in results if r['total_return'] > 0])} ({len([r for r in results if r['total_return'] > 0])/len(results)*100:.1f}%)")
    print(f"Losing strategies: {len([r for r in results if r['total_return'] <= 0])} ({len([r for r in results if r['total_return'] <= 0])/len(results)*100:.1f}%)")
    print(f"Average return: {np.mean([r['total_return'] for r in results]):.2f}%")
    print(f"Best return: {max([r['total_return'] for r in results]):.2f}%")
    print(f"Worst return: {min([r['total_return'] for r in results]):.2f}%")
    print(f"Average win rate: {np.mean([r['win_rate'] for r in results]):.1f}%")
    print(f"Average profit factor: {np.mean([r['profit_factor'] for r in results]):.2f}")
    
    # Save full results to JSON
    output_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'grid_search_results.json')
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\nFull results saved to: {output_file}")
    
    print()
    print(f"Finished at: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

if __name__ == '__main__':
    main()
