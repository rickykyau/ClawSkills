#!/usr/bin/env python3
"""
SMA Daily Trading Strategy Backtest v3
- HYBRID STOP LOSS: 10% Fixed from entry OR 15% Trailing from high (whichever loses less)
- 100-day SMA on QQQ daily close
- Trade TQQQ (3x leveraged)
- Signal Memory: after stop-out, re-enter if QQQ > SMA at close AND next open
- T+1 Cooldown: no same-day re-entry
"""

import argparse
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

def run_backtest(data_start='2021-01-01', backtest_start='2021-07-01', backtest_end='2026-02-05', 
                 capital=10000, sma_period=100, fixed_stop_pct=10, trailing_stop_pct=15, tax_rate=30):
    
    print("═"*100)
    print(" STRATEGY: QQQ Signal → TQQQ Trade (with Hybrid Stop Loss)")
    print("═"*100)
    print()
    print("| Rule           | Value                                                        |")
    print("|----------------|--------------------------------------------------------------|")
    print("| Signal Source  | QQQ daily close                                              |")
    print(f"| Indicator      | {sma_period}-day SMA                                                  |")
    print("| Trade Asset    | TQQQ (3x leveraged)                                          |")
    print("| Check Freq     | Every 15 minutes                                             |")
    print(f"| Fixed Stop     | {fixed_stop_pct}% from entry price                                         |")
    print(f"| Trailing Stop  | {trailing_stop_pct}% from highest price                                       |")
    print("| STOP LOGIC     | Use whichever stop is HIGHER (loses less)                    |")
    print("| BUY            | QQQ crosses above 100 SMA                                    |")
    print("| SELL           | QQQ crosses below 100 SMA OR stop hit                        |")
    print("| SIGNAL MEMORY  | After stop-out, if QQQ > SMA at close AND next open → re-enter |")
    print("| T+1 COOLDOWN   | No same-day re-entry after exit                              |")
    print()
    print(f"Period: {backtest_start} to {backtest_end}")
    print(f"Starting Capital: ${capital:,}")
    print()

    # Fetch data
    qqq = yf.download('QQQ', start=data_start, end=backtest_end, progress=False)
    tqqq = yf.download('TQQQ', start=data_start, end=backtest_end, progress=False)

    if isinstance(qqq.columns, pd.MultiIndex):
        qqq.columns = [c[0].lower() for c in qqq.columns]
        tqqq.columns = [c[0].lower() for c in tqqq.columns]
    else:
        qqq.columns = [c.lower() for c in qqq.columns]
        tqqq.columns = [c.lower() for c in tqqq.columns]

    qqq['sma'] = qqq['close'].rolling(window=sma_period).mean()
    qqq['above_sma'] = qqq['close'] > qqq['sma']

    common_idx = qqq.index.intersection(tqqq.index)
    qqq = qqq.loc[common_idx]
    tqqq = tqqq.loc[common_idx]

    backtest_start_dt = pd.to_datetime(backtest_start)
    qqq = qqq[qqq.index >= backtest_start_dt]
    tqqq = tqqq[tqqq.index >= backtest_start_dt]

    trades = []
    portfolio = capital
    position = None
    signal_memory = False
    t1_locked_until = None
    reentry_count = 0

    for i in range(1, len(qqq)):
        today = qqq.index[i]
        yesterday = qqq.index[i-1]
        today_date = today.date()
        
        qqq_close = qqq['close'].iloc[i]
        sma_today = qqq['sma'].iloc[i]
        above_sma_today = qqq_close > sma_today
        above_sma_yest = qqq['close'].iloc[i-1] > qqq['sma'].iloc[i-1]
        
        tqqq_open = tqqq['open'].iloc[i]
        tqqq_close = tqqq['close'].iloc[i]
        tqqq_high = tqqq['high'].iloc[i]
        
        if t1_locked_until and today_date <= t1_locked_until:
            if position:
                position['high_since_entry'] = max(position['high_since_entry'], tqqq_high)
            continue
        
        if position:
            position['high_since_entry'] = max(position['high_since_entry'], tqqq_high)
            
            # Calculate both stops
            fixed_stop = position['entry_price'] * (1 - fixed_stop_pct/100)
            trailing_stop = position['high_since_entry'] * (1 - trailing_stop_pct/100)
            
            # Use whichever is HIGHER (loses less)
            effective_stop = max(fixed_stop, trailing_stop)
            stop_type = 'TRAIL' if trailing_stop >= fixed_stop else 'FIXED'
            
            if tqqq_close <= effective_stop:
                exit_price = tqqq_close
                pnl = (exit_price - position['entry_price']) * position['shares']
                pnl_pct = (exit_price / position['entry_price'] - 1) * 100
                portfolio = portfolio + pnl
                days_held = (today - position['entry_date']).days
                
                trades.append({
                    'entry_date': position['entry_date'],
                    'entry_price': position['entry_price'],
                    'exit_date': today,
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'days': days_held,
                    'exit_reason': stop_type,
                    'entry_reason': position['entry_reason'],
                    'portfolio': portfolio,
                    'fixed_stop': fixed_stop,
                    'trailing_stop': trailing_stop,
                })
                
                signal_memory = above_sma_today
                position = None
                t1_locked_until = today_date + timedelta(days=1)
                continue
            
            if not above_sma_today and above_sma_yest:
                exit_price = tqqq_open
                pnl = (exit_price - position['entry_price']) * position['shares']
                pnl_pct = (exit_price / position['entry_price'] - 1) * 100
                portfolio = portfolio + pnl
                days_held = (today - position['entry_date']).days
                
                fixed_stop = position['entry_price'] * (1 - fixed_stop_pct/100)
                trailing_stop = position['high_since_entry'] * (1 - trailing_stop_pct/100)
                
                trades.append({
                    'entry_date': position['entry_date'],
                    'entry_price': position['entry_price'],
                    'exit_date': today,
                    'exit_price': exit_price,
                    'pnl': pnl,
                    'pnl_pct': pnl_pct,
                    'days': days_held,
                    'exit_reason': 'SMA',
                    'entry_reason': position['entry_reason'],
                    'portfolio': portfolio,
                    'fixed_stop': fixed_stop,
                    'trailing_stop': trailing_stop,
                })
                
                signal_memory = False
                position = None
                t1_locked_until = today_date + timedelta(days=1)
                continue
        
        else:
            if signal_memory:
                if above_sma_today:
                    entry_price = tqqq_open
                    shares = portfolio / entry_price
                    position = {
                        'entry_date': today,
                        'entry_price': entry_price,
                        'shares': shares,
                        'high_since_entry': tqqq_high,
                        'entry_reason': 'REENT'
                    }
                    signal_memory = False
                    reentry_count += 1
                    continue
                else:
                    signal_memory = False
            
            if above_sma_today and not above_sma_yest:
                entry_price = tqqq_open
                shares = portfolio / entry_price
                position = {
                    'entry_date': today,
                    'entry_price': entry_price,
                    'shares': shares,
                    'high_since_entry': tqqq_high,
                    'entry_reason': 'CROSS'
                }

    if position:
        exit_price = tqqq['close'].iloc[-1]
        pnl = (exit_price - position['entry_price']) * position['shares']
        pnl_pct = (exit_price / position['entry_price'] - 1) * 100
        portfolio = portfolio + pnl
        days_held = (qqq.index[-1] - position['entry_date']).days
        
        fixed_stop = position['entry_price'] * (1 - fixed_stop_pct/100)
        trailing_stop = position['high_since_entry'] * (1 - trailing_stop_pct/100)
        
        trades.append({
            'entry_date': position['entry_date'],
            'entry_price': position['entry_price'],
            'exit_date': qqq.index[-1],
            'exit_price': exit_price,
            'pnl': pnl,
            'pnl_pct': pnl_pct,
            'days': days_held,
            'exit_reason': 'END',
            'entry_reason': position['entry_reason'],
            'portfolio': portfolio,
            'fixed_stop': fixed_stop,
            'trailing_stop': trailing_stop,
        })

    qqq_start_price = qqq['close'].iloc[0]
    qqq_end_price = qqq['close'].iloc[-1]
    bh_final = capital * (qqq_end_price / qqq_start_price)

    print(f"TRADE LOG ({len(trades)} trades)")
    print("─"*120)
    print(f"{'#':<4} {'Entry':<12} {'Exit':<12} {'Entry$':>8} {'Exit$':>8} {'P&L%':>8} {'P&L$':>10} {'Days':>5} {'Exit':>6} {'Entry':>6} {'FixStop':>8} {'TrailStop':>10}")
    print("─"*120)
    
    for i, t in enumerate(trades):
        entry_str = t['entry_date'].strftime('%Y-%m-%d')
        exit_str = t['exit_date'].strftime('%Y-%m-%d')
        print(f"{i+1:<4} {entry_str:<12} {exit_str:<12} ${t['entry_price']:>6.2f} ${t['exit_price']:>6.2f} {t['pnl_pct']:>+7.1f}% ${t['pnl']:>+8.0f} {t['days']:>5} {t['exit_reason']:>6} {t['entry_reason']:>6} ${t['fixed_stop']:>6.2f} ${t['trailing_stop']:>8.2f}")
    
    print()

    # Summary
    total_return_pct = (portfolio / capital - 1) * 100
    bh_return_pct = (bh_final / capital - 1) * 100
    
    fixed_exits = len([t for t in trades if t['exit_reason'] == 'FIXED'])
    trail_exits = len([t for t in trades if t['exit_reason'] == 'TRAIL'])
    sma_exits = len([t for t in trades if t['exit_reason'] == 'SMA'])
    winning = [t for t in trades if t['pnl'] > 0]
    losing = [t for t in trades if t['pnl'] < 0]
    
    print("FINAL RESULTS")
    print("─"*100)
    print(f"Strategy Final:     ${portfolio:>10,.0f} ({total_return_pct:+.0f}%)")
    print(f"B&H QQQ Final:      ${bh_final:>10,.0f} ({bh_return_pct:+.0f}%)")
    print(f"Alpha vs QQQ:       {total_return_pct - bh_return_pct:>+.0f}%")
    print()
    print(f"Total Trades:       {len(trades)}")
    print(f"Fixed Stop Exits:   {fixed_exits}")
    print(f"Trailing Stop Exits:{trail_exits}")
    print(f"SMA Exits:          {sma_exits}")
    print(f"Re-Entry Trades:    {reentry_count}")
    print()
    
    win_rate = len(winning) / len(trades) * 100 if trades else 0
    avg_win = np.mean([t['pnl_pct'] for t in winning]) if winning else 0
    avg_loss = np.mean([t['pnl_pct'] for t in losing]) if losing else 0
    
    print(f"Win Rate:           {win_rate:.0f}% ({len(winning)}/{len(trades)})")
    print(f"Avg Win:            {avg_win:+.1f}%")
    print(f"Avg Loss:           {avg_loss:+.1f}%")
    print("═"*100)

    return trades


def main():
    parser = argparse.ArgumentParser(description='SMA Daily Trading Backtest v3 (Hybrid Stop)')
    parser.add_argument('--data-start', default='2021-01-01', help='Data start for SMA warmup')
    parser.add_argument('--start', default='2021-07-01', help='Backtest start date')
    parser.add_argument('--end', default='2026-02-05', help='Backtest end date')
    parser.add_argument('--capital', type=float, default=10000, help='Starting capital')
    parser.add_argument('--sma', type=int, default=100, help='SMA period')
    parser.add_argument('--fixed-stop', type=float, default=10, help='Fixed stop loss % from entry')
    parser.add_argument('--trailing-stop', type=float, default=15, help='Trailing stop % from high')
    parser.add_argument('--tax-rate', type=float, default=30, help='Tax rate on gains %')
    
    args = parser.parse_args()
    
    run_backtest(
        data_start=args.data_start,
        backtest_start=args.start,
        backtest_end=args.end,
        capital=args.capital,
        sma_period=args.sma,
        fixed_stop_pct=args.fixed_stop,
        trailing_stop_pct=args.trailing_stop,
        tax_rate=args.tax_rate
    )


if __name__ == '__main__':
    main()
