# SMA Daily Trading Strategy

Daily trend-following strategy using 100-day SMA with hybrid stop loss. Trades TQQQ based on QQQ signals.

---

## Strategy Rules

════════════════════════════════════════════════════════════════════════════════
 STRATEGY: QQQ Signal → TQQQ Trade (with Hybrid Stop Loss)
════════════════════════════════════════════════════════════════════════════════

| Rule           | Value                                                        |
|----------------|--------------------------------------------------------------|
| Signal Source  | QQQ daily close                                              |
| Indicator      | 100-day SMA                                                  |
| Trade Asset    | TQQQ (3x leveraged)                                          |
| Check Freq     | Every 15 minutes                                             |
| Fixed Stop     | 10% from entry price                                         |
| Trailing Stop  | 15% from highest price                                       |
| STOP LOGIC     | Use whichever stop is HIGHER (loses less)                    |
| BUY            | QQQ crosses above 100 SMA                                    |
| SELL           | QQQ crosses below 100 SMA OR stop hit                        |
| SIGNAL MEMORY  | After stop-out, if QQQ > SMA at close AND > SMA next open → re-enter |
| T+1 COOLDOWN   | No same-day re-entry after exit                              |

---

## Hybrid Stop Loss Logic

Two stop losses work together — use whichever is HIGHER (loses less money):

1. **Fixed Stop (10%)** — Protects from initial loss: `entry_price × 90%`
2. **Trailing Stop (15%)** — Locks in profits: `highest_price × 85%`

```
Entry at $100:
  Fixed stop = $90 (10% below entry)
  
Price at $110:
  Trailing stop = $93.50 (15% below high)
  Fixed stop = $90
  → Use $93.50 (trailing is higher)

Price at $120:
  Trailing stop = $102 (15% below high) 
  Fixed stop = $90
  → Use $102 (locks in profit!)
```

**Crossover point:** Trailing stop becomes higher than fixed stop once gain exceeds ~17.6%

---

## Signal Memory

After a **stop exit** (FIXED or TRAIL), re-enter only if QQQ confirms trend at BOTH checkpoints:

```
Without Signal Memory:
  Exit → Wait for NEW crossover above SMA (misses continuation)

With Signal Memory:
  Exit → Check QQQ > SMA at close AND at next open → Re-enter
```

**Rule:** Re-enter requires BOTH conditions:
1. ✅ QQQ > SMA at exit day's close (Signal Memory set)
2. ✅ QQQ > SMA at next trading day's open (Signal Memory confirmed)

**Why both checks?**
- Close check: Confirms trend intact after stop-out
- Open check: Prevents entering into overnight gap-down below SMA
- Avoids whipsaw of entering at open and exiting 15 min later

---

## Exit Rules Summary

| Exit Type | Trigger | Signal Memory |
|-----------|---------|---------------|
| **SMA Exit** | QQQ closes below 100d SMA | Cleared — need new crossover |
| **Fixed Stop** | Price drops 10% from entry | If QQQ > SMA at close AND next open → re-enter |
| **Trailing Stop** | Price drops 15% from peak | If QQQ > SMA at close AND next open → re-enter |

---

## Backtest Results (2021-07-01 to 2026-02-05)

| Metric | Value |
|--------|-------|
| Starting Capital | $10,000 |
| **Final Portfolio** | **$103,218** |
| **Total Return** | **+932%** |
| B&H QQQ Return | +76% |
| **Alpha vs QQQ** | **+857%** |
| Total Trades | 26 |
| Fixed Stop Exits | 1 |
| Trailing Stop Exits | 14 |
| SMA Exits | 11 |
| Re-Entry Trades | 8 |
| Win Rate | 73% (19/26) |
| Avg Win | +18.5% |
| Avg Loss | -8.7% |
| **After-Tax Alpha** | **$52,130 (+521%)** |

### Yearly Performance
```
Year   Strat Start   Strat End   Strat%   B&H%   Alpha%   Winner
────────────────────────────────────────────────────────────────
2021  $    10,000 $   12,905   +29.1%   +12%    +17%   Strat ✓
2022  $    12,905 $   13,914    +7.8%   -33%    +41%   Strat ✓
2023  $    13,914 $   30,767  +121.1%   +56%    +65%   Strat ✓
2024  $    30,767 $   69,491  +125.9%   +28%    +98%   Strat ✓
2025  $    69,491 $  103,218   +48.5%   +21%    +28%   Strat ✓
2026  $   103,218 $  103,218    +0.0%    -1%     +1%   Strat ✓
```

---

## Standard Output Format

### Header
```
════════════════════════════════════════════════════════════════════════════════
 STRATEGY: QQQ Signal → TQQQ Trade (with Hybrid Stop Loss)
════════════════════════════════════════════════════════════════════════════════

| Rule           | Value                                                        |
|----------------|--------------------------------------------------------------|
| Signal Source  | QQQ daily close                                              |
| Indicator      | 100-day SMA                                                  |
| Trade Asset    | TQQQ (3x leveraged)                                          |
| Check Freq     | Every 15 minutes                                             |
| Fixed Stop     | 10% from entry price                                         |
| Trailing Stop  | 15% from highest price                                       |
| STOP LOGIC     | Use whichever stop is HIGHER (loses less)                    |
| BUY            | QQQ crosses above 100 SMA                                    |
| SELL           | QQQ crosses below 100 SMA OR stop hit                        |
| SIGNAL MEMORY  | After stop-out, if QQQ > SMA at close AND next open → re-enter |
| T+1 COOLDOWN   | No same-day re-entry after exit                              |

Period: YYYY-MM-DD to YYYY-MM-DD
Starting Capital: $X,XXX
```

### Trade Log
```
TRADE LOG (X trades)
────────────────────────────────────────────────────────────────────────────────────────────
#   Entry        Exit         Entry$   Exit$    P&L%    P&L$   Days  Exit   Entry  FixStop  TrailStop
────────────────────────────────────────────────────────────────────────────────────────────
1   2023-01-20   2023-02-10   $19.89   $23.28  +17.1%  $1,210   21  TRAIL  CROSS   $17.90    $19.78
2   2023-03-13   2023-08-09   $21.07   $39.92  +89.4%  $7,431  149  TRAIL  REENT   $18.96    $33.93
```

| Column | Description |
|--------|-------------|
| # | Trade number |
| Entry | Entry date |
| Exit | Exit date |
| Entry$ | TQQQ entry price |
| Exit$ | TQQQ exit price |
| P&L% | Percentage gain/loss |
| P&L$ | Dollar gain/loss |
| Days | Holding period |
| Exit | Exit reason: `FIXED`, `TRAIL`, or `SMA` |
| Entry | Entry reason: `CROSS` (SMA crossover) or `REENT` (Signal Memory re-entry) |
| FixStop | Fixed stop price (entry × 90%) |
| TrailStop | Trailing stop price (high × 85%) |

### Yearly Summary
```
YEARLY SUMMARY
────────────────────────────────────────────────────────────────────────────────────────────
Year  Strat Start  Strat End  Strat%  Strat P/L  PostTax%  B&H Start  B&H End   B&H%  B&H P/L  Alpha%  #Trades  #Stops  Winner
```

### Final Results
```
FINAL RESULTS
────────────────────────────────────────────────────────────────────────────────
Strategy Final:     $X (+X%)
B&H QQQ Final:      $X (+X%)
Alpha vs QQQ:       +X%

Total Trades:       X
Fixed Stop Exits:   X
Trailing Stop Exits:X
SMA Exits:          X
Re-Entry Trades:    X

Win Rate:           X% (X/X)
Avg Win:            +X%
Avg Loss:           -X%
```

### After-Tax Summary
```
AFTER-TAX SUMMARY
────────────────────────────────────────────────────────────────────────────────
Strategy After-Tax P/L:   $X
B&H QQQ After-Tax P/L:    $X
After-Tax Alpha:          $X (+X%)
```

Tax calculation: 30% on all gains (simplified short-term capital gains rate)

---

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `sma_period` | int | 100 | SMA period (days) |
| `fixed_stop` | float | 10 | Fixed stop loss % from entry |
| `trailing_stop` | float | 15 | Trailing stop % from high |
| `signal_source` | string | QQQ | Asset for SMA signal |
| `trade_asset` | string | TQQQ | Asset to trade |
| `tax_rate` | float | 30 | Tax rate on gains (%) |

---

## Usage

```bash
# Basic backtest (uses defaults: 10% fixed, 15% trailing)
python scripts/backtest_v3.py

# With custom dates
python scripts/backtest_v3.py --start 2021-07-01 --end 2026-02-05

# With custom stop parameters
python scripts/backtest_v3.py --fixed-stop 10 --trailing-stop 15

# With custom capital
python scripts/backtest_v3.py --capital 50000
```

---

## Files

```
sma-daily-trading/
├── SKILL.md           # This file
├── scripts/
│   ├── backtest.py    # Legacy backtest script
│   ├── backtest_v2.py # Trailing stop only version
│   └── backtest_v3.py # Current: Hybrid stop (fixed + trailing)
└── results/           # Backtest output files
```

---

## Changelog

| Date | Change |
|------|--------|
| 2025-02-05 | Initial strategy with 15% trailing stop |
| 2025-02-06 | Added Signal Memory rules for re-entry after stop-out |
| 2025-02-06 | Upgraded to hybrid stop loss (10% fixed + 15% trailing) |
| 2025-02-06 | Backtest results: +932% return, +857% alpha vs QQQ |
