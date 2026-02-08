#!/usr/bin/env python3
"""
QQQ Signal → TQQQ Trading - Massive Strategy Test
Uses 5 years of 15-min data, tests 1000+ strategies in batches
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

def fetch_5yr_data(client, symbol):
    """Fetch 5 years of 15-min data in chunks (API limits)"""
    all_data = []
    end = datetime.now()
    
    # Fetch in 30-day chunks to avoid API limits
    for i in range(60):  # ~5 years = 60 months
        chunk_end = end - timedelta(days=30*i)
        chunk_start = chunk_end - timedelta(days=30)
        
        if chunk_start.year < 2020:  # Stop at 2020
            break
            
        try:
            req = StockBarsRequest(
                symbol_or_symbols=symbol,
                timeframe=TimeFrame(15, TimeFrameUnit.Minute),
                start=chunk_start,
                end=chunk_end,
                feed='iex'
            )
            bars = client.get_stock_bars(req)
            if bars and symbol in bars.data:
                for b in bars.data[symbol]:
                    all_data.append({
                        'timestamp': b.timestamp,
                        'open': float(b.open),
                        'high': float(b.high),
                        'low': float(b.low),
                        'close': float(b.close),
                        'volume': int(b.volume)
                    })
        except Exception as e:
            print(f"  Chunk {i} error: {e}")
            continue
    
    if not all_data:
        return None
    
    df = pd.DataFrame(all_data)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    df = df.drop_duplicates(subset='timestamp')
    df = df.set_index('timestamp').sort_index()
    return df

def calculate_indicators(df, rsi_period, macd_fast, macd_slow, macd_signal, bb_period=20, bb_std=2):
    """Calculate all technical indicators on QQQ data"""
    close = df['close']
    
    # RSI
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(window=rsi_period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
    rs = gain / loss.replace(0, np.nan)
    df['rsi'] = 100 - (100 / (1 + rs))
    
    # MACD
    ema_fast = close.ewm(span=macd_fast, adjust=False).mean()
    ema_slow = close.ewm(span=macd_slow, adjust=False).mean()
    df['macd'] = ema_fast - ema_slow
    df['macd_signal'] = df['macd'].ewm(span=macd_signal, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']
    
    # Bollinger Bands
    df['bb_mid'] = close.rolling(window=bb_period).mean()
    df['bb_std'] = close.rolling(window=bb_period).std()
    df['bb_upper'] = df['bb_mid'] + (bb_std * df['bb_std'])
    df['bb_lower'] = df['bb_mid'] - (bb_std * df['bb_std'])
    df['bb_pct'] = (close - df['bb_lower']) / (df['bb_upper'] - df['bb_lower'])
    
    # EMA crossovers
    df['ema_9'] = close.ewm(span=9, adjust=False).mean()
    df['ema_21'] = close.ewm(span=21, adjust=False).mean()
    df['ema_50'] = close.ewm(span=50, adjust=False).mean()
    
    # Volume indicators
    df['vol_sma'] = df['volume'].rolling(window=20).mean()
    df['vol_ratio'] = df['volume'] / df['vol_sma']
    
    return df

def run_backtest(qqq_df, tqqq_df, params):
    """Run backtest: signals from QQQ, trade TQQQ"""
    
    # Store TQQQ close before merge
    tqqq_close = tqqq_df[['close']].rename(columns={'close': 'tqqq_close'})
    
    if len(qqq_df) < 200:
        return None
    
    # Calculate indicators on QQQ first
    qqq_df = calculate_indicators(qqq_df, 
        params['rsi_period'], params['macd_fast'], 
        params['macd_slow'], params['macd_signal'])
    
    # Now merge with TQQQ
    merged = qqq_df.join(tqqq_close, how='inner')
    
    merged = merged.dropna()
    if len(merged) < 100:
        return None
    
    # Rename for clarity
    merged = merged.rename(columns={'close': 'qqq_close'})
    
    # Generate signals based on strategy
    strategy = params['strategy']
    
    # RSI signals
    rsi_buy = merged['rsi'] < params['rsi_oversold']
    rsi_sell = merged['rsi'] > params['rsi_overbought']
    
    # MACD signals
    macd_buy = (merged['macd'] > merged['macd_signal']) & \
               (merged['macd'].shift(1) <= merged['macd_signal'].shift(1))
    macd_sell = (merged['macd'] < merged['macd_signal']) & \
                (merged['macd'].shift(1) >= merged['macd_signal'].shift(1))
    
    # Bollinger Band signals
    bb_buy = merged['bb_pct'] < 0.1
    bb_sell = merged['bb_pct'] > 0.9
    
    # EMA signals
    ema_buy = (merged['ema_9'] > merged['ema_21']) & \
              (merged['ema_9'].shift(1) <= merged['ema_21'].shift(1))
    ema_sell = (merged['ema_9'] < merged['ema_21']) & \
               (merged['ema_9'].shift(1) >= merged['ema_21'].shift(1))
    
    # Volume filter
    vol_confirm = merged['vol_ratio'] > 1.2
    
    # Combine based on strategy
    if strategy == 'rsi_only':
        buy_signal = rsi_buy
        sell_signal = rsi_sell
    elif strategy == 'macd_only':
        buy_signal = macd_buy
        sell_signal = macd_sell
    elif strategy == 'bb_only':
        buy_signal = bb_buy
        sell_signal = bb_sell
    elif strategy == 'ema_only':
        buy_signal = ema_buy
        sell_signal = ema_sell
    elif strategy == 'rsi_macd':
        buy_signal = rsi_buy & macd_buy
        sell_signal = rsi_sell | macd_sell
    elif strategy == 'rsi_bb':
        buy_signal = rsi_buy & bb_buy
        sell_signal = rsi_sell | bb_sell
    elif strategy == 'macd_bb':
        buy_signal = macd_buy & bb_buy
        sell_signal = macd_sell | bb_sell
    elif strategy == 'rsi_vol':
        buy_signal = rsi_buy & vol_confirm
        sell_signal = rsi_sell
    elif strategy == 'macd_vol':
        buy_signal = macd_buy & vol_confirm
        sell_signal = macd_sell
    elif strategy == 'triple':
        buy_signal = rsi_buy & macd_buy & bb_buy
        sell_signal = rsi_sell | macd_sell | bb_sell
    else:  # all_combined
        buy_signal = (rsi_buy | macd_buy | bb_buy) & vol_confirm
        sell_signal = rsi_sell | macd_sell | bb_sell
    
    # Simulate trading on TQQQ
    initial_capital = 10000
    capital = initial_capital
    position = 0
    entry_price = 0
    entry_time = None
    trades = []
    
    sl_pct = params['stop_loss'] / 100
    tp_pct = params['take_profit'] / 100
    
    for idx in merged.index:
        row = merged.loc[idx]
        tqqq_price = row['tqqq_close']
        
        if position > 0:
            pnl_pct = (tqqq_price - entry_price) / entry_price
            
            # Check exit conditions
            exit_reason = None
            if pnl_pct <= -sl_pct:
                exit_reason = 'stop_loss'
            elif pnl_pct >= tp_pct:
                exit_reason = 'take_profit'
            elif sell_signal.loc[idx]:
                exit_reason = 'signal'
            
            if exit_reason:
                pnl = position * (tqqq_price - entry_price)
                capital += position * tqqq_price
                trades.append({
                    'entry_time': str(entry_time),
                    'exit_time': str(idx),
                    'entry_price': round(entry_price, 2),
                    'exit_price': round(tqqq_price, 2),
                    'pnl': round(pnl, 2),
                    'pnl_pct': round(pnl_pct * 100, 2),
                    'exit_reason': exit_reason
                })
                position = 0
        
        else:
            # Check entry
            if buy_signal.loc[idx] and capital > 0:
                position = capital / tqqq_price
                entry_price = tqqq_price
                entry_time = idx
                capital = 0
    
    # Close any open position
    if position > 0:
        final_price = merged.iloc[-1]['tqqq_close']
        pnl = position * (final_price - entry_price)
        capital += position * final_price
        trades.append({
            'entry_time': str(entry_time),
            'exit_time': str(merged.index[-1]),
            'entry_price': round(entry_price, 2),
            'exit_price': round(final_price, 2),
            'pnl': round(pnl, 2),
            'pnl_pct': round(((final_price - entry_price) / entry_price) * 100, 2),
            'exit_reason': 'end_of_data'
        })
    
    if not trades:
        return None
    
    # Calculate metrics
    total_return = ((capital - initial_capital) / initial_capital) * 100
    wins = [t for t in trades if t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] <= 0]
    
    win_rate = len(wins) / len(trades) * 100
    avg_win = np.mean([t['pnl_pct'] for t in wins]) if wins else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losses]) if losses else 0
    
    gross_profit = sum(t['pnl'] for t in wins) if wins else 0
    gross_loss = abs(sum(t['pnl'] for t in losses)) if losses else 0.01
    profit_factor = gross_profit / gross_loss
    
    # Max drawdown
    equity = [initial_capital]
    for t in trades:
        equity.append(equity[-1] + t['pnl'])
    peak = equity[0]
    max_dd = 0
    for e in equity:
        if e > peak:
            peak = e
        dd = (peak - e) / peak * 100
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
        'final_capital': round(capital, 2),
        'trades': trades  # Include for validation
    }

def main():
    print("=" * 70, flush=True)
    print("QQQ SIGNAL → TQQQ TRADING - MASSIVE STRATEGY TEST", flush=True)
    print("=" * 70, flush=True)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)
    
    client = StockHistoricalDataClient(API_KEY, SECRET_KEY)
    
    # Fetch data
    print("\nFetching 5 years of 15-min data...", flush=True)
    print("  QQQ...", end=" ", flush=True)
    qqq_df = fetch_5yr_data(client, 'QQQ')
    if qqq_df is not None:
        print(f"✓ {len(qqq_df)} bars ({qqq_df.index.min().date()} to {qqq_df.index.max().date()})", flush=True)
    else:
        print("✗ Failed", flush=True)
        return
    
    print("  TQQQ...", end=" ", flush=True)
    tqqq_df = fetch_5yr_data(client, 'TQQQ')
    if tqqq_df is not None:
        print(f"✓ {len(tqqq_df)} bars ({tqqq_df.index.min().date()} to {tqqq_df.index.max().date()})", flush=True)
    else:
        print("✗ Failed", flush=True)
        return
    
    # Strategy parameters grid
    strategies = [
        'rsi_only', 'macd_only', 'bb_only', 'ema_only',
        'rsi_macd', 'rsi_bb', 'macd_bb', 
        'rsi_vol', 'macd_vol', 'triple', 'all_combined'
    ]
    
    rsi_periods = [7, 9, 14, 21]
    rsi_oversold_levels = [20, 25, 30, 35]
    rsi_overbought_levels = [65, 70, 75, 80]
    macd_settings = [(8, 21, 9), (12, 26, 9), (8, 17, 9), (5, 13, 8)]
    stop_losses = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]
    take_profits = [1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]
    
    # Count total combinations
    total_combos = (len(strategies) * len(rsi_periods) * len(rsi_oversold_levels) * 
                   len(rsi_overbought_levels) * len(macd_settings) * 
                   len(stop_losses) * len(take_profits))
    
    print(f"\nTotal strategy combinations: {total_combos}", flush=True)
    print("\nRunning backtests in batches...", flush=True)
    
    all_results = []
    batch_num = 0
    tested = 0
    
    # Run in batches by strategy type
    for strat in strategies:
        batch_num += 1
        batch_results = []
        
        print(f"\n[Batch {batch_num}/{len(strategies)}] Strategy: {strat}", flush=True)
        
        for rsi_p in rsi_periods:
            for rsi_os in rsi_oversold_levels:
                for rsi_ob in rsi_overbought_levels:
                    for macd_f, macd_s, macd_sig in macd_settings:
                        for sl in stop_losses:
                            for tp in take_profits:
                                tested += 1
                                
                                params = {
                                    'strategy': strat,
                                    'rsi_period': rsi_p,
                                    'rsi_oversold': rsi_os,
                                    'rsi_overbought': rsi_ob,
                                    'macd_fast': macd_f,
                                    'macd_slow': macd_s,
                                    'macd_signal': macd_sig,
                                    'stop_loss': sl,
                                    'take_profit': tp
                                }
                                
                                result = run_backtest(qqq_df.copy(), tqqq_df.copy(), params)
                                if result:
                                    batch_results.append(result)
        
        all_results.extend(batch_results)
        
        if batch_results:
            best = max(batch_results, key=lambda x: x['total_return'])
            print(f"  Valid: {len(batch_results)} | Best return: {best['total_return']:+.1f}% | "
                  f"Trades: {best['num_trades']} | Win rate: {best['win_rate']:.0f}%", flush=True)
        else:
            print(f"  Valid: 0", flush=True)
        
        # Progress
        pct = tested / total_combos * 100
        print(f"  Progress: {pct:.0f}% ({tested}/{total_combos})", flush=True)
    
    print(f"\n{'='*70}", flush=True)
    print(f"COMPLETED: {len(all_results)} valid strategies out of {total_combos} tested", flush=True)
    print(f"{'='*70}", flush=True)
    
    if not all_results:
        print("No valid results!")
        return
    
    # TOP 20 BY RETURN
    print("\n🏆 TOP 20 BY TOTAL RETURN:", flush=True)
    print("-" * 70, flush=True)
    
    by_return = sorted(all_results, key=lambda x: x['total_return'], reverse=True)[:20]
    for i, r in enumerate(by_return, 1):
        p = r['params']
        print(f"\n{i}. RETURN: {r['total_return']:+.1f}% | Strategy: {p['strategy']}", flush=True)
        print(f"   Trades: {r['num_trades']} | Win Rate: {r['win_rate']:.0f}% | "
              f"PF: {r['profit_factor']:.2f} | Max DD: {r['max_drawdown']:.1f}%", flush=True)
        print(f"   RSI({p['rsi_period']}) OS:{p['rsi_oversold']} OB:{p['rsi_overbought']} | "
              f"MACD({p['macd_fast']},{p['macd_slow']},{p['macd_signal']})", flush=True)
        print(f"   Stop Loss: {p['stop_loss']}% | Take Profit: {p['take_profit']}%", flush=True)
        
        # Show sample trades for #1
        if i == 1:
            print(f"\n   Sample trades from best strategy:", flush=True)
            for t in r['trades'][:5]:
                print(f"   - Entry: {t['entry_time']} @ ${t['entry_price']} → "
                      f"Exit: {t['exit_time']} @ ${t['exit_price']} | "
                      f"P/L: {t['pnl_pct']:+.1f}% ({t['exit_reason']})", flush=True)
    
    # TOP 15 BY PROFIT FACTOR
    print(f"\n{'='*70}", flush=True)
    print("📊 TOP 15 BY PROFIT FACTOR (min 20 trades):", flush=True)
    print("-" * 70, flush=True)
    
    by_pf = sorted([r for r in all_results if r['num_trades'] >= 20], 
                   key=lambda x: x['profit_factor'], reverse=True)[:15]
    for i, r in enumerate(by_pf, 1):
        p = r['params']
        print(f"{i:2}. PF: {r['profit_factor']:5.2f} | Return: {r['total_return']:+6.1f}% | "
              f"{p['strategy']:12} | Trades: {r['num_trades']:3} | Win: {r['win_rate']:4.0f}%", flush=True)
    
    # TOP 15 BY WIN RATE
    print(f"\n{'='*70}", flush=True)
    print("🎯 TOP 15 BY WIN RATE (min 20 trades):", flush=True)
    print("-" * 70, flush=True)
    
    by_wr = sorted([r for r in all_results if r['num_trades'] >= 20], 
                   key=lambda x: x['win_rate'], reverse=True)[:15]
    for i, r in enumerate(by_wr, 1):
        p = r['params']
        print(f"{i:2}. Win: {r['win_rate']:5.1f}% | Return: {r['total_return']:+6.1f}% | "
              f"{p['strategy']:12} | Trades: {r['num_trades']:3} | PF: {r['profit_factor']:5.2f}", flush=True)
    
    # SUMMARY
    print(f"\n{'='*70}", flush=True)
    print("SUMMARY STATISTICS", flush=True)
    print("=" * 70, flush=True)
    
    profitable = len([r for r in all_results if r['total_return'] > 0])
    print(f"Total strategies tested: {len(all_results)}", flush=True)
    print(f"Profitable: {profitable} ({profitable/len(all_results)*100:.1f}%)", flush=True)
    print(f"Average return: {np.mean([r['total_return'] for r in all_results]):.2f}%", flush=True)
    print(f"Best return: {max(r['total_return'] for r in all_results):.2f}%", flush=True)
    print(f"Worst return: {min(r['total_return'] for r in all_results):.2f}%", flush=True)
    
    print("\nBY STRATEGY TYPE:", flush=True)
    for strat in strategies:
        sr = [r for r in all_results if r['params']['strategy'] == strat]
        if sr:
            prof = len([r for r in sr if r['total_return'] > 0]) / len(sr) * 100
            best = max(r['total_return'] for r in sr)
            avg = np.mean([r['total_return'] for r in sr])
            print(f"  {strat:15}: {len(sr):4} strategies | Best: {best:+6.1f}% | "
                  f"Avg: {avg:+5.1f}% | {prof:4.0f}% profitable", flush=True)
    
    # Save full results
    output_file = os.path.join(script_dir, 'qqq_tqqq_results.json')
    
    # Save top 100 with full trade details
    top_100 = sorted(all_results, key=lambda x: x['total_return'], reverse=True)[:100]
    with open(output_file, 'w') as f:
        json.dump(top_100, f, indent=2, default=str)
    print(f"\nTop 100 results saved to: {output_file}", flush=True)
    
    # Save summary without trade details for all results
    summary_file = os.path.join(script_dir, 'qqq_tqqq_summary.json')
    summary = [{k: v for k, v in r.items() if k != 'trades'} for r in all_results]
    with open(summary_file, 'w') as f:
        json.dump(summary, f, indent=2, default=str)
    print(f"All results summary saved to: {summary_file}", flush=True)
    
    print(f"\nFinished: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", flush=True)

if __name__ == '__main__':
    main()
