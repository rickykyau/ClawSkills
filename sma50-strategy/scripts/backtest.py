#!/usr/bin/env python3
"""
SMA(50) Crossover Backtest Engine — with slippage/commission model.
Based on validated V9 engine (32+ QC trade matches).

Features:
- SMA50 crossover signal on QQQ, trades TQQQ
- Fixed stop (7.5%) + trailing stop (15%)
- EOD daily close check with next-open exit
- T+1 cooldown bypass after EOD exits
- Gap-through slippage handling
- Configurable slippage & commission
"""
import argparse
import os
import sys
import pandas as pd
import numpy as np

def parse_args():
    p = argparse.ArgumentParser(description="SMA50 Crossover Backtest")
    p.add_argument("--start-date", type=str, default=None)
    p.add_argument("--end-date", type=str, default=None)
    p.add_argument("--capital", type=float, default=10000.0)
    p.add_argument("--sma-period", type=int, default=50)
    p.add_argument("--fixed-stop", type=float, default=0.075)
    p.add_argument("--trailing-stop", type=float, default=0.15)
    p.add_argument("--slippage", type=float, default=0.0005, help="Slippage per trade as fraction (default 0.05%%)")
    p.add_argument("--commission", type=float, default=0.0, help="Commission per trade in dollars")
    p.add_argument("--signal-ticker", type=str, default="QQQ")
    p.add_argument("--trade-ticker", type=str, default="TQQQ")
    p.add_argument("--cache-dir", type=str, default=os.path.expanduser("~/clawd/skills/technical-backtesting/cache"))
    p.add_argument("--no-slippage", action="store_true", help="Disable slippage for comparison")
    return p.parse_args()

def load_data(cache_dir):
    qqq_daily = pd.read_csv(f"{cache_dir}/qqq_daily_adj.csv", index_col=0, parse_dates=True)
    tqqq_15 = pd.read_csv(f"{cache_dir}/tqqq_15min_adj.csv", index_col=0, parse_dates=True)
    qqq_15 = pd.read_csv(f"{cache_dir}/qqq_15min_adj.csv", index_col=0, parse_dates=True)
    for df in [qqq_daily, tqqq_15, qqq_15]:
        df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")
    def mh(df):
        mins = df.index.hour * 60 + df.index.minute
        return df[(mins >= 9*60+30) & (mins < 16*60)]
    return qqq_daily, mh(tqqq_15), mh(qqq_15)

def apply_slippage(price, direction, slippage_pct):
    """Apply slippage: buying costs more, selling gets less."""
    if direction == "buy":
        return price * (1 + slippage_pct)
    else:
        return price * (1 - slippage_pct)

def run_backtest(qqq_daily, tqqq_15, qqq_15, args):
    slippage = 0.0 if args.no_slippage else args.slippage
    commission = args.commission

    qqq_daily = qqq_daily.sort_index()
    qqq_daily["sma"] = qqq_daily["close"].rolling(args.sma_period).mean()

    sma_by_date = {}
    daily_close_by_date = {}
    for idx in qqq_daily.index:
        d = idx.date()
        if not np.isnan(qqq_daily.loc[idx, "sma"]):
            sma_by_date[d] = qqq_daily.loc[idx, "sma"]
            daily_close_by_date[d] = qqq_daily.loc[idx, "close"]

    common_ts = tqqq_15.index.intersection(qqq_15.index).sort_values()

    # Optional date filter
    if args.start_date:
        start = pd.Timestamp(args.start_date, tz="America/New_York")
        common_ts = common_ts[common_ts >= start]
    if args.end_date:
        end = pd.Timestamp(args.end_date, tz="America/New_York") + pd.Timedelta(days=1)
        common_ts = common_ts[common_ts < end]

    last_bar_of_day = {}
    first_bar_of_day = {}
    for ts in common_ts:
        d = ts.date()
        last_bar_of_day[d] = ts
        if d not in first_bar_of_day:
            first_bar_of_day[d] = ts

    FIXED_STOP_PCT = args.fixed_stop
    TRAILING_STOP_PCT = args.trailing_stop
    capital = args.capital
    shares = 0.0
    entry_price = 0.0
    highest = 0.0
    last_exit_date = None
    last_exit_was_eod = False
    trades = []
    in_position = False
    prev_above_sma = None
    pending_eod_exit = False
    total_slippage_cost = 0.0
    total_commission_cost = 0.0

    for ts in common_ts:
        d = ts.date()
        prev_sma_dates = [sd for sd in sma_by_date if sd < d]
        if not prev_sma_dates:
            continue
        sma_val = sma_by_date[max(prev_sma_dates)]
        qqq_price = qqq_15.loc[ts, "close"]
        tqqq_close = tqqq_15.loc[ts, "close"]
        tqqq_high = tqqq_15.loc[ts, "high"]
        tqqq_low = tqqq_15.loc[ts, "low"]
        above_sma = qqq_price > sma_val

        if prev_above_sma is None:
            prev_above_sma = above_sma
            continue

        is_first_bar = (ts == first_bar_of_day.get(d))

        # Handle pending EOD exit at market open
        if pending_eod_exit and is_first_bar and in_position:
            raw_exit_price = tqqq_close
            fill_price = apply_slippage(raw_exit_price, "sell", slippage)
            slip_cost = shares * abs(raw_exit_price - fill_price)
            total_slippage_cost += slip_cost
            total_commission_cost += commission
            pnl = shares * (fill_price - entry_price) - commission
            capital = shares * fill_price - commission
            trades[-1].update({
                "exit_dt": ts, "exit_price": fill_price, "raw_exit_price": raw_exit_price,
                "pnl": round(pnl, 2), "exit_reason": "SMA EXIT (EOD)",
                "slippage_cost": round(slip_cost, 2), "commission": commission,
            })
            in_position = False
            shares = 0
            last_exit_date = d
            last_exit_was_eod = True
            pending_eod_exit = False
            prev_above_sma = False

        if pending_eod_exit and is_first_bar:
            pending_eod_exit = False

        # CHECK EXITS
        if in_position:
            if tqqq_high > highest:
                highest = tqqq_high
            fixed_stop = entry_price * (1 - FIXED_STOP_PCT)
            trailing_stop = highest * (1 - TRAILING_STOP_PCT)
            active_stop = max(fixed_stop, trailing_stop)
            exit_reason = None
            raw_exit_price = None
            is_last_bar = (ts == last_bar_of_day.get(d))

            if tqqq_low <= active_stop:
                exit_reason = "STOP"
                if tqqq_high < active_stop:
                    raw_exit_price = tqqq_close
                else:
                    raw_exit_price = active_stop
            elif prev_above_sma and not above_sma and not is_last_bar:
                exit_reason = "SMA EXIT"
                raw_exit_price = tqqq_close

            if exit_reason:
                fill_price = apply_slippage(raw_exit_price, "sell", slippage)
                slip_cost = shares * abs(raw_exit_price - fill_price)
                total_slippage_cost += slip_cost
                total_commission_cost += commission
                pnl = shares * (fill_price - entry_price) - commission
                capital = shares * fill_price - commission
                trades[-1].update({
                    "exit_dt": ts, "exit_price": fill_price, "raw_exit_price": raw_exit_price,
                    "pnl": round(pnl, 2), "exit_reason": exit_reason,
                    "slippage_cost": round(slip_cost, 2), "commission": commission,
                })
                in_position = False
                shares = 0
                last_exit_date = d
                last_exit_was_eod = False

        # CHECK ENTRIES
        elif not prev_above_sma and above_sma:
            if last_exit_date == d and not last_exit_was_eod:
                prev_above_sma = above_sma
                continue
            raw_entry_price = tqqq_close
            entry_price = apply_slippage(raw_entry_price, "buy", slippage)
            slip_cost_entry = (entry_price - raw_entry_price)  # per share
            total_commission_cost += commission
            capital -= commission
            shares = capital / entry_price
            slip_cost = shares * abs(entry_price - raw_entry_price)
            total_slippage_cost += slip_cost
            highest = tqqq_high
            trades.append({
                "trade_num": len(trades) + 1, "entry_dt": ts,
                "entry_price": entry_price, "raw_entry_price": raw_entry_price,
                "exit_dt": None, "exit_price": None, "raw_exit_price": None,
                "pnl": None, "exit_reason": None,
                "slippage_cost": round(slip_cost, 2), "commission": commission,
                "_entry_capital": capital, "_shares": shares,
            })
            in_position = True
            last_exit_was_eod = False

        prev_above_sma = above_sma

        # EOD check
        if ts == last_bar_of_day.get(d) and d in sma_by_date and d in daily_close_by_date:
            eod_close = daily_close_by_date[d]
            eod_sma = sma_by_date[d]
            eod_above = eod_close > eod_sma
            if in_position and not eod_above:
                pending_eod_exit = True
            prev_above_sma = eod_above

    # Close open position
    if in_position and trades and trades[-1]["exit_dt"] is None:
        last_price = tqqq_15.iloc[-1]["close"]
        fill_price = apply_slippage(last_price, "sell", slippage)
        slip_cost = shares * abs(last_price - fill_price)
        total_slippage_cost += slip_cost
        pnl = shares * (fill_price - entry_price)
        trades[-1].update({
            "exit_dt": tqqq_15.index[-1], "exit_price": fill_price,
            "raw_exit_price": last_price,
            "pnl": round(pnl, 2), "exit_reason": "OPEN",
            "slippage_cost": round(slip_cost, 2), "commission": 0,
        })
        capital = shares * fill_price

    return trades, capital, total_slippage_cost, total_commission_cost

def load_benchmark(cache_dir, ticker, start_date=None, end_date=None):
    """Load daily benchmark data (SPY or QQQ) for buy-and-hold comparison."""
    path = f"{cache_dir}/{ticker.lower()}_daily_adj.csv"
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, index_col=0, parse_dates=True)
    df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")
    df = df.sort_index()
    if start_date:
        df = df[df.index >= pd.Timestamp(start_date, tz="America/New_York")]
    if end_date:
        df = df[df.index <= pd.Timestamp(end_date, tz="America/New_York") + pd.Timedelta(days=1)]
    return df


def compute_yearly_breakdown(trades, starting_capital):
    """Compute per-year stats from trade list."""
    if not trades:
        return {}

    # Build a running capital series by trade
    yearly = {}
    running_capital = starting_capital

    for t in trades:
        if t['pnl'] is None:
            continue
        exit_dt = t['exit_dt']
        if exit_dt is None:
            continue
        year = exit_dt.year
        if year not in yearly:
            yearly[year] = {
                'begin_bal': running_capital,
                'trades': [],
                'stops': 0,
            }
        yearly[year]['trades'].append(t)
        if t['exit_reason'] == 'STOP':
            yearly[year]['stops'] += 1
        running_capital += t['pnl']
        yearly[year]['end_bal'] = running_capital

    return yearly


def print_report(trades, capital, total_slippage, total_commission, args):
    slippage_label = f"{args.slippage*100:.2f}%" if not args.no_slippage else "OFF"
    TAX_RATE = 0.30  # short-term capital gains

    print(f"\n{'='*80}")
    print(f"SMA({args.sma_period}) CROSSOVER BACKTEST — {args.signal_ticker} signal / {args.trade_ticker} trades")
    print(f"Slippage: {slippage_label} | Commission: ${args.commission:.2f}/trade")
    print(f"Fixed Stop: {args.fixed_stop*100:.1f}% | Trailing Stop: {args.trailing_stop*100:.1f}%")
    print(f"Starting Capital: ${args.capital:,.2f}")
    print(f"{'='*80}")

    # ── YEARLY BREAKDOWN ──
    yearly = compute_yearly_breakdown(trades, args.capital)
    if yearly:
        print(f"\n{'─'*80}")
        print(f"  YEARLY BREAKDOWN")
        print(f"{'─'*80}")
        print(f"{'Year':>6} | {'Begin Bal':>12} | {'End Bal':>12} | {'P&L $':>12} | {'P&L %':>8} | {'Post-Tax':>12} | {'Trades':>6} | {'Win%':>6} | {'Stops':>5}")
        print(f"{'─'*6}-+-{'─'*12}-+-{'─'*12}-+-{'─'*12}-+-{'─'*8}-+-{'─'*12}-+-{'─'*6}-+-{'─'*6}-+-{'─'*5}")

        for year in sorted(yearly.keys()):
            y = yearly[year]
            yr_trades = y['trades']
            yr_pnl = sum(t['pnl'] for t in yr_trades)
            yr_wins = sum(1 for t in yr_trades if t['pnl'] > 0)
            yr_wr = yr_wins / len(yr_trades) * 100 if yr_trades else 0
            yr_pct = yr_pnl / y['begin_bal'] * 100 if y['begin_bal'] else 0
            yr_post_tax = yr_pnl * (1 - TAX_RATE) if yr_pnl > 0 else yr_pnl  # losses not taxed
            print(f"{year:>6} | ${y['begin_bal']:>11,.2f} | ${y['end_bal']:>11,.2f} | ${yr_pnl:>+11,.2f} | {yr_pct:>+7.1f}% | ${yr_post_tax:>+11,.2f} | {len(yr_trades):>6} | {yr_wr:>5.1f}% | {y['stops']:>5}")

        print(f"{'─'*80}")

    # ── TRADE LIST ──
    wins = [t for t in trades if t['pnl'] and t['pnl'] > 0]
    losses = [t for t in trades if t['pnl'] and t['pnl'] <= 0]
    closed = [t for t in trades if t['exit_reason'] != 'OPEN']
    total_pnl = sum(t['pnl'] for t in trades if t['pnl'])

    print(f"\n{'#':>3} | {'Entry DateTime':>18} | {'Exit DateTime':>18} | {'Entry $':>10} | {'Exit $':>10} | {'P&L $':>10} | {'P&L %':>8} | {'Days':>5} | Exit Reason")
    print("-" * 115)
    for t in trades:
        ed = t["entry_dt"].strftime("%Y-%m-%d %H:%M") if t["entry_dt"] else ""
        xd = t["exit_dt"].strftime("%Y-%m-%d %H:%M") if t["exit_dt"] else ""
        ep = f"${t['entry_price']:.2f}"
        xp = f"${t['exit_price']:.2f}" if t['exit_price'] else ""
        pnl_amt = f"${t['pnl']:+,.2f}" if t['pnl'] else ""
        pnl_pct = f"{t['pnl']/t['entry_price']/t.get('_shares',1)*100/100:+.1f}%" if t['pnl'] and t.get('_shares') else ""
        # Calculate P&L % based on capital at entry
        if t['pnl'] is not None and t.get('_entry_capital'):
            pnl_pct = f"{t['pnl']/t['_entry_capital']*100:+.1f}%"
        elif t['pnl'] is not None and t['entry_price']:
            pnl_pct = f"{(t['exit_price']/t['entry_price']-1)*100:+.1f}%"
        days = ""
        if t["entry_dt"] and t["exit_dt"]:
            days = str((t["exit_dt"].date() - t["entry_dt"].date()).days)
        r = t["exit_reason"] or ""
        # Clean up exit reason labels
        if r == "STOP":
            r = "Stop Out"
        elif "SMA" in r:
            r = "SMA Out"
        print(f"{t['trade_num']:>3} | {ed:>18} | {xd:>18} | {ep:>10} | {xp:>10} | {pnl_amt:>10} | {pnl_pct:>8} | {days:>5} | {r}")
    print("-" * 115)

    # ── SUMMARY ──
    stop_trades = [t for t in closed if t['exit_reason'] == 'STOP']
    post_tax_pnl = total_pnl * (1 - TAX_RATE) if total_pnl > 0 else total_pnl
    post_tax_pct = post_tax_pnl / args.capital * 100

    print(f"\n{'='*80}")
    print(f"  SUMMARY")
    print(f"{'='*80}")
    print(f"  Total Trades:        {len(trades)}")
    print(f"  Stop Losses:         {len(stop_trades)}")
    print(f"  Win Rate:            {len(wins)/max(len(closed),1)*100:.1f}%")
    print(f"  P&L Amount:          ${total_pnl:>+,.2f}")
    print(f"  P&L %:               {total_pnl/args.capital*100:>+.1f}%")
    print(f"  Post-Tax P&L (30%):  ${post_tax_pnl:>+,.2f}")
    print(f"  Post-Tax Return:     {post_tax_pct:>+.1f}%")
    print(f"  Slippage Cost:       ${total_slippage:>,.2f}")
    if wins:
        print(f"  Avg Win:             ${sum(t['pnl'] for t in wins)/len(wins):>,.2f}")
    if losses:
        print(f"  Avg Loss:            ${sum(t['pnl'] for t in losses)/len(losses):>,.2f}")

    # ── BUY & HOLD COMPARISON ──
    print(f"\n{'─'*80}")
    print(f"  BUY & HOLD COMPARISON")
    print(f"{'─'*80}")

    # Determine backtest date range from trades
    if trades:
        bt_start = trades[0]['entry_dt']
        bt_end = trades[-1]['exit_dt'] or trades[-1]['entry_dt']
        total_days = (bt_end - bt_start).days

        for ticker in ['SPY', 'QQQ']:
            bench = load_benchmark(args.cache_dir, ticker, args.start_date, args.end_date)
            if bench is not None and len(bench) > 1:
                bh_start_price = bench.iloc[0]['close']
                bh_end_price = bench.iloc[-1]['close']
                bh_pnl_pct = (bh_end_price / bh_start_price - 1) * 100
                bh_pnl_amt = args.capital * bh_pnl_pct / 100
                # Tax: 15% if held >12 months, 30% if <=12 months
                bh_tax_rate = 0.15 if total_days > 365 else 0.30
                bh_post_tax = bh_pnl_amt * (1 - bh_tax_rate) if bh_pnl_amt > 0 else bh_pnl_amt
                bh_post_tax_pct = bh_post_tax / args.capital * 100
                print(f"  {ticker} Buy & Hold:     ${bh_pnl_amt:>+,.2f} ({bh_pnl_pct:>+.1f}%)")
                print(f"  {ticker} Post-Tax ({int(bh_tax_rate*100)}%): ${bh_post_tax:>+,.2f} ({bh_post_tax_pct:>+.1f}%)")

    print(f"{'='*80}")

def main():
    args = parse_args()
    print("Loading data...", flush=True)
    qqq_daily, tqqq_15, qqq_15 = load_data(args.cache_dir)
    print(f"TQQQ 15m: {len(tqqq_15)}, QQQ 15m: {len(qqq_15)}", flush=True)

    trades, capital, total_slip, total_comm = run_backtest(qqq_daily, tqqq_15, qqq_15, args)
    print_report(trades, capital, total_slip, total_comm, args)
    return trades, capital

if __name__ == "__main__":
    main()
