#!/usr/bin/env python3
"""
Compare SMA strategy across different ETF pairs
Signal ETF (100d SMA) → Trade 3x leveraged version
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

# ETF pairs to test: (signal_etf, trade_etf, name)
ETF_PAIRS = [
    ('QQQ', 'TQQQ', 'Nasdaq 100'),
    ('SPY', 'UPRO', 'S&P 500'),
    ('IWM', 'TNA', 'Russell 2000'),
    ('SOXX', 'SOXL', 'Semiconductors'),
    ('DIA', 'UDOW', 'Dow Jones 30'),
]

# Parameters
DATA_START = '2021-01-01'
BACKTEST_START = '2021-07-01'
BACKTEST_END = '2026-02-05'
CAPITAL = 10000
SMA_PERIOD = 100
FIXED_STOP_PCT = 10
TRAILING_STOP_PCT = 15

def run_backtest(signal_etf, trade_etf, name):
    """Run backtest for a single ETF pair"""
    
    # Fetch data
    signal_data = yf.download(signal_etf, start=DATA_START, end=BACKTEST_END, progress=False)
    trade_data = yf.download(trade_etf, start=DATA_START, end=BACKTEST_END, progress=False)
    
    if len(signal_data) == 0 or len(trade_data) == 0:
        return None
    
    # Flatten columns
    if isinstance(signal_data.columns, pd.MultiIndex):
        signal_data.columns = [c[0].lower() for c in signal_data.columns]
        trade_data.columns = [c[0].lower() for c in trade_data.columns]
    else:
        signal_data.columns = [c.lower() for c in signal_data.columns]
        trade_data.columns = [c.lower() for c in trade_data.columns]
    
    # Calculate SMA
    signal_data['sma'] = signal_data['close'].rolling(window=SMA_PERIOD).mean()
    
    # Align data
    common_idx = signal_data.index.intersection(trade_data.index)
    signal_data = signal_data.loc[common_idx]
    trade_data = trade_data.loc[common_idx]
    
    # Filter to backtest period
    backtest_start_dt = pd.to_datetime(BACKTEST_START)
    signal_data = signal_data[signal_data.index >= backtest_start_dt]
    trade_data = trade_data[trade_data.index >= backtest_start_dt]
    
    if len(signal_data) < 10:
        return None
    
    # Trading simulation
    trades = []
    portfolio = CAPITAL
    position = None
    signal_memory = False
    t1_locked_until = None
    
    for i in range(1, len(signal_data)):
        today = signal_data.index[i]
        today_date = today.date()
        
        signal_close = signal_data['close'].iloc[i]
        sma_today = signal_data['sma'].iloc[i]
        above_sma_today = signal_close > sma_today
        above_sma_yest = signal_data['close'].iloc[i-1] > signal_data['sma'].iloc[i-1]
        
        trade_open = trade_data['open'].iloc[i]
        trade_close = trade_data['close'].iloc[i]
        trade_high = trade_data['high'].iloc[i]
        
        if t1_locked_until and today_date <= t1_locked_until:
            if position:
                position['high_since_entry'] = max(position['high_since_entry'], trade_high)
            continue
        
        if position:
            position['high_since_entry'] = max(position['high_since_entry'], trade_high)
            
            fixed_stop = position['entry_price'] * (1 - FIXED_STOP_PCT/100)
            trailing_stop = position['high_since_entry'] * (1 - TRAILING_STOP_PCT/100)
            effective_stop = max(fixed_stop, trailing_stop)
            
            if trade_close <= effective_stop:
                pnl = (trade_close - position['entry_price']) * position['shares']
                portfolio = portfolio + pnl
                trades.append({'pnl': pnl, 'pnl_pct': (trade_close / position['entry_price'] - 1) * 100})
                signal_memory = above_sma_today
                position = None
                t1_locked_until = today_date + timedelta(days=1)
                continue
            
            if not above_sma_today and above_sma_yest:
                pnl = (trade_open - position['entry_price']) * position['shares']
                portfolio = portfolio + pnl
                trades.append({'pnl': pnl, 'pnl_pct': (trade_open / position['entry_price'] - 1) * 100})
                signal_memory = False
                position = None
                t1_locked_until = today_date + timedelta(days=1)
                continue
        else:
            if signal_memory and above_sma_today:
                position = {
                    'entry_price': trade_open,
                    'shares': portfolio / trade_open,
                    'high_since_entry': trade_high,
                }
                signal_memory = False
                continue
            elif signal_memory:
                signal_memory = False
            
            if above_sma_today and not above_sma_yest:
                position = {
                    'entry_price': trade_open,
                    'shares': portfolio / trade_open,
                    'high_since_entry': trade_high,
                }
    
    # Close open position
    if position:
        pnl = (trade_data['close'].iloc[-1] - position['entry_price']) * position['shares']
        portfolio = portfolio + pnl
        trades.append({'pnl': pnl, 'pnl_pct': (trade_data['close'].iloc[-1] / position['entry_price'] - 1) * 100})
    
    # B&H signal ETF
    bh_start = signal_data['close'].iloc[0]
    bh_end = signal_data['close'].iloc[-1]
    bh_return = (bh_end / bh_start - 1) * 100
    bh_final = CAPITAL * (1 + bh_return/100)
    
    # Stats
    total_return = (portfolio / CAPITAL - 1) * 100
    winning = [t for t in trades if t['pnl'] > 0]
    losing = [t for t in trades if t['pnl'] < 0]
    win_rate = len(winning) / len(trades) * 100 if trades else 0
    avg_win = np.mean([t['pnl_pct'] for t in winning]) if winning else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losing]) if losing else 0
    
    return {
        'name': name,
        'signal': signal_etf,
        'trade': trade_etf,
        'final': portfolio,
        'return_pct': total_return,
        'bh_final': bh_final,
        'bh_return': bh_return,
        'alpha': total_return - bh_return,
        'trades': len(trades),
        'win_rate': win_rate,
        'avg_win': avg_win,
        'avg_loss': avg_loss,
    }


# Run all backtests
print("═"*100)
print(" SMA STRATEGY COMPARISON: Signal ETF → Trade 3x Leveraged")
print("═"*100)
print(f"Period: {BACKTEST_START} to {BACKTEST_END}")
print(f"Parameters: {SMA_PERIOD}d SMA, {FIXED_STOP_PCT}% fixed stop, {TRAILING_STOP_PCT}% trailing stop")
print()

results = []
for signal, trade, name in ETF_PAIRS:
    print(f"Testing {signal}/{trade} ({name})...", end=" ")
    result = run_backtest(signal, trade, name)
    if result:
        results.append(result)
        print(f"✓ Return: {result['return_pct']:+.0f}%")
    else:
        print("✗ No data")

# Sort by return
results.sort(key=lambda x: x['return_pct'], reverse=True)

print()
print("═"*100)
print(" RESULTS RANKED BY RETURN")
print("═"*100)
print()
print(f"{'Rank':<5} {'Signal':<8} {'Trade':<8} {'Sector':<18} {'Final':>12} {'Return':>10} {'B&H Ret':>10} {'Alpha':>10} {'Trades':>8} {'Win%':>8}")
print("─"*100)

for i, r in enumerate(results):
    print(f"{i+1:<5} {r['signal']:<8} {r['trade']:<8} {r['name']:<18} ${r['final']:>10,.0f} {r['return_pct']:>+9.0f}% {r['bh_return']:>+9.0f}% {r['alpha']:>+9.0f}% {r['trades']:>8} {r['win_rate']:>7.0f}%")

print()
print("═"*100)
print(" WINNER: " + results[0]['signal'] + "/" + results[0]['trade'] + f" ({results[0]['name']}) with {results[0]['return_pct']:+.0f}% return")
print("═"*100)
