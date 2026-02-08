# Technical Backtesting Framework

A reusable intraday backtesting framework validated against QuantConnect. Built for strategies that use daily indicators to generate signals on intraday bars.

## Data Fetching

### Alpaca API
Credentials in `.env`:
```
ALPACA_API_KEY=...
ALPACA_SECRET_KEY=...
```

Fetch daily + intraday bars for any ticker:
```python
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame

client = StockHistoricalDataClient(api_key, secret_key)
request = StockBarsRequest(
    symbol_or_symbols="QQQ",
    timeframe=TimeFrame(15, TimeFrame.TimeFrameUnit.Minute),  # or TimeFrame.Day
    start=datetime(2021, 1, 1),
    end=datetime(2026, 1, 1),
    adjustment=Adjustment.SPLIT,  # Critical — see pitfalls
    feed="iex",
)
bars = client.get_stock_bars(request)
```

**Data feed**: IEX (free tier, 15-min delayed for live — historical is fine for backtesting).

### Data Cache
Location: `~/clawd/skills/technical-backtesting/cache/`

Structure:
```
cache/
  {ticker}_daily_adj.csv      # Daily OHLCV, split-adjusted
  {ticker}_15min_adj.csv      # 15-min OHLCV, split-adjusted
```

CSV format: DatetimeIndex (UTC), columns: `open, high, low, close, volume, trade_count, vwap`

Refresh with: `~/clawd/skills/sma50-strategy/scripts/fetch_data.py` (adapt for new tickers).

## Backtest Engine Architecture

### Core Pattern: Daily Indicator → Intraday Signals

The fundamental pattern for strategies that compute indicators on daily bars but trade on intraday bars:

```
Daily bars → Compute indicator (SMA, RSI, etc.)
Intraday bars → Compare price vs PREVIOUS DAY's indicator value
                Generate entry/exit signals
EOD → Compare daily close vs TODAY's indicator value
       Override/correct intraday state
```

### Key Mechanisms (Validated Against QC)

#### 1. Previous Day's Indicator Reference
**Never use today's daily indicator for intraday signals.** At any intraday bar, you only know yesterday's daily close and indicator value. Today's daily bar isn't complete yet.

```python
# Correct: use most recent completed daily indicator
prev_dates = [d for d in indicator_by_date if d < today]
indicator_val = indicator_by_date[max(prev_dates)]

# Wrong: using today's indicator intraday (lookahead bias)
```

#### 2. EOD Check (End-of-Day Reconciliation)
At the last bar of each day, compare the daily close against today's actual indicator value. This catches cases where intraday signals disagree with the daily picture.

```python
if ts == last_bar_of_day[date] and date in indicator_by_date:
    eod_value = indicator_by_date[date]  # Today's actual daily value
    if in_position and should_exit_on_daily(eod_value):
        pending_exit = True  # Queue exit for next market open
    prev_signal_state = daily_signal_state  # Reset to daily truth
```

**Why next-open exit?** The daily close confirms the signal, but you can't execute at the close — you exit at next day's open bar close price.

#### 3. No Signal Exits on Last Bar of Day
If the last intraday bar triggers a signal exit, **don't take it** — let the EOD check handle it. This prevents double-counting and matches QC behavior.

```python
if signal_exit_triggered and not is_last_bar:
    execute_exit()
# If it IS the last bar, the EOD check will decide
```

#### 4. Gap-Through Stop Slippage
When a stop loss is hit, check if the price actually traded through the stop level:

```python
if bar_low <= stop_price:
    if bar_high < stop_price:
        # Entire bar is below stop — gap through, can't fill at stop
        fill_price = bar_close
    else:
        # Bar crossed the stop level — fill at stop price
        fill_price = stop_price
```

This models real-world slippage on gap downs where no liquidity exists at the stop price.

#### 5. T+1 Cooldown with EOD Bypass
After exiting a position, don't re-enter on the same day (prevents whipsaw). **Exception**: if the exit was an EOD-triggered exit (executed at next open), allow re-entry on the same day since the exit was forced by end-of-day reconciliation.

```python
if last_exit_date == today and not last_exit_was_eod:
    skip_entry()  # T+1 cooldown
# EOD exits allow same-day re-entry because they execute at open
```

#### 6. Market Hours Filtering
Filter intraday bars to regular trading hours only:

```python
def market_hours(df):
    mins = df.index.hour * 60 + df.index.minute
    return df[(mins >= 9*60+30) & (mins < 16*60)]  # 9:30 AM - 4:00 PM ET
```

Always convert timestamps to `America/New_York` before filtering.

#### 7. Slippage & Commission Model
Apply after the engine determines the theoretical fill price:

```python
def apply_slippage(price, direction, slippage_pct):
    if direction == "buy":
        return price * (1 + slippage_pct)  # Pay more
    else:
        return price * (1 - slippage_pct)  # Receive less
```

Default: 0.05% per trade. Commission: $0 for Alpaca. Both configurable.

## Validation Methodology

### Trade-for-Trade QC Comparison

The gold standard is matching every trade against a QuantConnect backtest over the same period.

**Match criteria:**
- **Full match (✓)**: Entry date matches, exit date within ±1 day, P&L direction (win/loss) matches
- **Partial match (~)**: Entry date matches but exit or P&L direction differs
- **Mismatch (✗)**: Entry dates don't align

**Why ±1 day on exits?** Minor differences in bar alignment, data feed timing, and EOD handling can shift exits by a day. Direction agreement is more important than exact P&L.

**QC trades file**: `qc_trades.csv` — exported from QuantConnect with columns:
```
Entry Time, Symbols, Exit Time, Direction, Entry Price, Exit Price, Quantity, P&L, Fees, Drawdown, IsWin, Order Ids
```

### Comparison Script Pattern
```python
for i in range(max(len(my_trades), len(qc_trades))):
    my = my_trades[i]
    qc = qc_trades.iloc[i]
    entry_match = my_entry_date == qc_entry_date
    exit_match = abs(my_exit_date - qc_exit_date) <= 1 day
    pnl_match = (my_pnl > 0) == (qc_pnl > 0)
```

## Common Pitfalls

### 1. Split Adjustment (Critical)
**Always use split-adjusted data**, especially for leveraged ETFs like TQQQ that have had reverse splits. Raw prices will produce completely wrong results.

Use `adjustment=Adjustment.SPLIT` (not `ALL` — dividend adjustment distorts leveraged ETF prices).

### 2. SMA Reference Timing
Using today's SMA for intraday decisions is lookahead bias. You must use the previous day's completed SMA. This is the single most common source of mismatches.

### 3. Stop Fill Price Assumptions
Assuming stops fill at the stop price ignores gaps. A stock can gap down 5% past your stop. The gap-through model (fill at close when entire bar is below stop) is more realistic.

### 4. Timezone Handling
Alpaca returns UTC timestamps. Convert to ET before market hours filtering or date grouping:
```python
df.index = pd.to_datetime(df.index, utc=True).tz_convert("America/New_York")
```

### 5. Multi-Index from Alpaca
When fetching a single symbol, Alpaca still returns a MultiIndex `(symbol, timestamp)`. Drop level 0:
```python
df = bars.df
if isinstance(df.index, pd.MultiIndex):
    df = df.droplevel(0)
```

### 6. Last Bar vs EOD Conflict
If you process signal exits on the last bar AND run the EOD check, you can double-exit or miss the EOD override. Always skip signal exits on the last bar.

## Creating a New Strategy

1. **Copy the template**: Use `~/clawd/skills/sma50-strategy/scripts/backtest.py` as a starting point
2. **Replace the signal logic**: Change what generates entry/exit signals (the indicator and crossover condition)
3. **Keep the framework**: EOD check, gap-through stops, T+1 cooldown, market hours filter — these are battle-tested
4. **Create a skill folder**: `~/clawd/skills/{strategy-name}/` with `SKILL.md` and `scripts/`
5. **Validate against QC**: Run the same strategy in QuantConnect and compare trade-for-trade
6. **Add slippage**: Use the slippage model to get realistic P&L estimates

### Strategy Skill Structure
```
skills/{strategy-name}/
  SKILL.md              # Strategy rules, how to run, interpret results
  scripts/
    backtest.py         # Main engine (copy from sma50, replace signal logic)
    fetch_data.py       # Data fetcher (adapt tickers)
    compare_qc.py       # QC validation (adapt trade format)
```

## File Index
```
skills/technical-backtesting/
  SKILL.md              # This file — framework documentation
  .env                  # Alpaca credentials
  qc_trades.csv         # QuantConnect reference trades (SMA50)
  cache/                # Cached market data
    qqq_daily_adj.csv
    qqq_15min_adj.csv
    tqqq_15min_adj.csv
  scripts/
    sma50_v9.py         # Original validated engine (hardcoded)
    sma50_validated.py   # Same as v9 (frozen reference)
    sma50_realistic.py   # V9 + slippage model
```

## Python Environment
```bash
~/clawd/venv/bin/python  # Use this venv for all backtests
```
