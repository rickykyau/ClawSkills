# SMA50 Crossover Strategy

## Overview
Trend-following strategy that uses QQQ's 50-day SMA as a signal to trade TQQQ (3x leveraged QQQ).

## Strategy Rules

### Signal
- **Indicator**: QQQ price vs its 50-day Simple Moving Average (SMA50)
- **Signal source**: Previous day's daily SMA value (no lookahead)
- **Intraday check**: QQQ 15-minute bars compared against yesterday's SMA50

### Entry
- **Trigger**: QQQ crosses ABOVE SMA50 (previous bar below, current bar above)
- **Action**: Buy TQQQ at bar close price
- **Position sizing**: 100% of capital

### Exit — Three Mechanisms
1. **Fixed Stop**: 7.5% below entry price
2. **Trailing Stop**: 15% below highest high since entry
3. **SMA Exit**: QQQ crosses BELOW SMA50 intraday → sell TQQQ at bar close

### EOD (End-of-Day) Check
- At market close, compare QQQ daily close vs today's SMA50 (using today's actual daily data)
- If position is open and daily close < SMA50 → **queue exit for next market open**
- This prevents overnight exposure when the trend has reversed

### Gap-Through Slippage
- If a stop is hit but the entire bar is below the stop level (gap-through), fill at bar close instead of stop price
- Models real-world slippage on gap downs

### T+1 Cooldown
- After an intraday exit, no re-entry allowed on the same day
- **Exception**: After an EOD exit (executed at next open), re-entry IS allowed on the same day
- This matches QuantConnect's behavior

## Key Implementation Details
- Uses **split-adjusted** data (not dividend-adjusted) for accurate TQQQ pricing
- SMA calculated on daily bars, signals checked on 15-minute bars
- Market hours filter: 9:30 AM - 4:00 PM ET only
- The "active stop" is `max(fixed_stop, trailing_stop)` — whichever is higher

## Slippage Model
- Default: 0.05% per trade (entry and exit)
- Buying: price * (1 + slippage) — you pay more
- Selling: price * (1 - slippage) — you receive less
- Commission: $0 default (Alpaca is commission-free), configurable

## Running Backtests

```bash
# Default run (with 0.05% slippage)
~/clawd/venv/bin/python ~/clawd/skills/sma50-strategy/scripts/backtest.py

# No slippage (for QC comparison)
~/clawd/venv/bin/python ~/clawd/skills/sma50-strategy/scripts/backtest.py --no-slippage

# Custom parameters
~/clawd/venv/bin/python ~/clawd/skills/sma50-strategy/scripts/backtest.py \
  --capital 25000 --sma-period 50 --slippage 0.001 --fixed-stop 0.075

# Compare against QuantConnect
~/clawd/venv/bin/python ~/clawd/skills/sma50-strategy/scripts/compare_qc.py

# Refresh data cache
~/clawd/venv/bin/python ~/clawd/skills/sma50-strategy/scripts/fetch_data.py
```

## File Locations
- **Backtest engine**: `scripts/backtest.py`
- **QC comparison**: `scripts/compare_qc.py`
- **Data fetcher**: `scripts/fetch_data.py`
- **Data cache**: `~/clawd/skills/technical-backtesting/cache/`
- **QC trades**: `~/clawd/skills/technical-backtesting/qc_trades.csv`
- **Alpaca credentials**: `~/clawd/skills/technical-backtesting/.env`

## Interpreting Results
- **Full match (✓)**: Entry date, exit date (±1 day), and P&L direction all match QC
- **Partial match (~)**: Entry date matches but exit or P&L direction differs
- **Mismatch (✗)**: Entry dates don't align
- Slippage impact shows the total $ cost of the slippage model vs ideal fills
