# ClawSkills

Centralized repository for Clawdbot skills and trading strategies.

## Skills

| Skill | Description | Status |
|-------|-------------|--------|
| [sma-daily-trading](./sma-daily-trading/) | QQQ/TQQQ SMA trend-following with hybrid stop loss | ✅ Active |

## Structure

Each skill follows this structure:
```
skill-name/
├── SKILL.md           # Strategy documentation
├── scripts/           # Python scripts
│   └── backtest.py    # Backtesting script
└── results/           # Output files, reports
```

## sma-daily-trading

**Strategy:** 100-day SMA on QQQ → Trade TQQQ (3x leveraged)

**Performance (7/1/21 - 2/5/26):**
- Return: **+932%**
- Alpha vs QQQ B&H: **+857%**
- Win Rate: 73%

See [sma-daily-trading/SKILL.md](./sma-daily-trading/SKILL.md) for full details.
