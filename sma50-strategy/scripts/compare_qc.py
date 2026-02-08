#!/usr/bin/env python3
"""
Compare backtest output against QuantConnect trades CSV.
Runs both no-slippage and with-slippage versions and compares.
"""
import os
import sys
import pandas as pd

# Add parent to path so we can import backtest
sys.path.insert(0, os.path.dirname(__file__))
from backtest import load_data, run_backtest

QC_PATH = os.path.expanduser("~/clawd/skills/technical-backtesting/qc_trades.csv")
CACHE_DIR = os.path.expanduser("~/clawd/skills/technical-backtesting/cache")

class Args:
    def __init__(self, **kwargs):
        defaults = dict(
            start_date=None, end_date=None, capital=10000.0,
            sma_period=50, fixed_stop=0.075, trailing_stop=0.15,
            slippage=0.0005, commission=0.0,
            signal_ticker="QQQ", trade_ticker="TQQQ",
            cache_dir=CACHE_DIR, no_slippage=False,
        )
        defaults.update(kwargs)
        for k, v in defaults.items():
            setattr(self, k, v)

def main():
    print("Loading data...", flush=True)
    qqq_daily, tqqq_15, qqq_15 = load_data(CACHE_DIR)

    # Run no-slippage
    args_no = Args(no_slippage=True)
    trades_no, cap_no, slip_no, comm_no = run_backtest(qqq_daily.copy(), tqqq_15, qqq_15, args_no)

    # Run with slippage
    args_slip = Args(no_slippage=False)
    trades_slip, cap_slip, slip_slip, comm_slip = run_backtest(qqq_daily.copy(), tqqq_15, qqq_15, args_slip)

    # Load QC
    qc = pd.read_csv(QC_PATH)

    pnl_no = sum(t['pnl'] for t in trades_no if t['pnl'])
    pnl_slip = sum(t['pnl'] for t in trades_slip if t['pnl'])
    pnl_qc = qc['P&L'].sum()

    print(f"\n{'='*90}")
    print(f"COMPARISON: No-Slippage vs With-Slippage (0.05%) vs QuantConnect")
    print(f"{'='*90}")
    print(f"{'Metric':<25} | {'No Slippage':>15} | {'With Slippage':>15} | {'QC':>15}")
    print(f"{'-'*25}-+-{'-'*15}-+-{'-'*15}-+-{'-'*15}")
    print(f"{'Trades':<25} | {len(trades_no):>15} | {len(trades_slip):>15} | {len(qc):>15}")
    wins_no = len([t for t in trades_no if t['pnl'] and t['pnl'] > 0])
    wins_slip = len([t for t in trades_slip if t['pnl'] and t['pnl'] > 0])
    wins_qc = qc['IsWin'].sum()
    print(f"{'Wins':<25} | {wins_no:>15} | {wins_slip:>15} | {int(wins_qc):>15}")
    print(f"{'Total P&L':<25} | ${pnl_no:>13,.2f} | ${pnl_slip:>13,.2f} | ${pnl_qc:>13,.2f}")
    print(f"{'Final Capital':<25} | ${cap_no:>13,.2f} | ${cap_slip:>13,.2f} | {'N/A':>15}")
    print(f"{'Return':<25} | {pnl_no/10000*100:>14.1f}% | {pnl_slip/10000*100:>14.1f}% | {pnl_qc/10000*100:>14.1f}%")
    print(f"{'Slippage Cost':<25} | ${slip_no:>13,.2f} | ${slip_slip:>13,.2f} | {'N/A':>15}")
    print(f"{'Slippage Impact':<25} | {'N/A':>15} | ${pnl_no-pnl_slip:>13,.2f} | {'N/A':>15}")

    # Trade-by-trade comparison
    print(f"\n{'#':>3} | {'No-Slip Entry':>12} | {'Slip Entry':>12} | {'QC Entry':>12} | {'No-Slip P&L':>12} | {'Slip P&L':>12} | {'QC P&L':>12} | Match")
    print("-" * 105)

    full_matches = 0
    n = max(len(trades_no), len(trades_slip), len(qc))
    for i in range(n):
        tn = trades_no[i] if i < len(trades_no) else None
        ts = trades_slip[i] if i < len(trades_slip) else None
        qr = qc.iloc[i] if i < len(qc) else None

        ne = tn["entry_dt"].strftime("%Y-%m-%d") if tn else ""
        se = ts["entry_dt"].strftime("%Y-%m-%d") if ts else ""
        qe = pd.to_datetime(qr["Entry Time"]).strftime("%Y-%m-%d") if qr is not None else ""
        np_ = f"${tn['pnl']:+,.2f}" if tn and tn['pnl'] else ""
        sp = f"${ts['pnl']:+,.2f}" if ts and ts['pnl'] else ""
        qp = f"${qr['P&L']:+,.2f}" if qr is not None else ""

        match = ""
        if tn and qr is not None:
            em = ne == qe
            nx = tn["exit_dt"].strftime("%Y-%m-%d") if tn["exit_dt"] else ""
            qx = pd.to_datetime(qr["Exit Time"]).strftime("%Y-%m-%d")
            xm = nx == qx or (tn["exit_dt"] and abs((tn["exit_dt"].date() - pd.to_datetime(qr["Exit Time"]).date()).days) <= 1)
            pm = (tn['pnl'] > 0) == (qr['P&L'] > 0) if tn['pnl'] else False
            if em and xm and pm:
                match = "✓"
                full_matches += 1
            elif em:
                match = "~"
            else:
                match = "✗"

        print(f"{i+1:>3} | {ne:>12} | {se:>12} | {qe:>12} | {np_:>12} | {sp:>12} | {qp:>12} | {match:>5}")

    print("-" * 105)
    print(f"\nFull matches (no-slip vs QC): {full_matches}/{min(len(trades_no), len(qc))}")

if __name__ == "__main__":
    main()
