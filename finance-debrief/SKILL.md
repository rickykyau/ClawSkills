# Finance Debrief — Daily Finance Research & Debrief

Daily global markets research with actionable summary. Run each morning before market open.

---

## Overview

| Field | Value |
|-------|-------|
| **Purpose** | Morning finance research & debrief |
| **Frequency** | Daily, before US market open (9:30 AM ET) |
| **Output** | Structured brief with actionable insights |
| **Data Sources** | Web search, financial APIs, news feeds |

---

## Research Sections

### 1. Global News Research

**Geopolitical Events:**
- Middle East (Iran, Israel, Saudi, Yemen, Syria)
- China (Taiwan, economy, US relations, trade policy)
- Russia-Ukraine conflict updates
- North Korea developments
- European Union / ECB policy
- Latin America (Venezuela, Argentina, Brazil, Mexico)
- India, Southeast Asia tensions

**Market-Moving News:**
- Central bank announcements (Fed, ECB, BOJ, PBOC)
- Earnings surprises (major companies)
- M&A activity
- Regulatory changes
- Supply chain disruptions
- Commodity shocks (oil, gas, metals)
- Currency crises
- Natural disasters affecting markets

**What to Flag:**
- Military incidents or escalations
- Surprise policy announcements
- Major index moves (>1% overnight)
- Currency/commodity spikes

---

### 2. Market Overview

**Asia Session (closed by US morning):**
- Nikkei 225 (Japan)
- Hang Seng (Hong Kong)
- Shanghai Composite (China)
- KOSPI (South Korea)
- ASX 200 (Australia)

**Europe Session (in progress):**
- FTSE 100 (UK)
- DAX (Germany)
- CAC 40 (France)
- Euro Stoxx 50

**US Pre-Market:**
- S&P 500 futures (ES)
- Nasdaq futures (NQ)
- Dow futures (YM)
- VIX (volatility)

**Commodities & Crypto:**
- Gold (XAU)
- Silver (XAG)
- Crude Oil (WTI, Brent)
- Bitcoin (BTC)
- Ethereum (ETH)

**Currencies:**
- DXY (Dollar Index)
- EUR/USD
- USD/JPY
- USD/CNY

---

### 3. Actionable Summary

**Format:**
```
## Today's Summary — [DATE]

**Market Sentiment:** [Bullish/Bearish/Neutral] — [1-line reason]

**Top 3 Things to Watch:**
1. [Event/data point] — [Why it matters]
2. [Event/data point] — [Why it matters]
3. [Event/data point] — [Why it matters]

**Risk Factors:**
- [Key risk to monitor]
- [Key risk to monitor]

**Trading Implications:**
- [Sector/asset to favor or avoid]
- [Specific action if applicable]
```

---

## Output Template

```markdown
# Finance Debrief — [DATE]

## 🌏 Global News

### Geopolitical
- **[Region]:** [Brief summary of development]
- **[Region]:** [Brief summary of development]

### Market-Moving
- **[Category]:** [News item and impact]
- **[Category]:** [News item and impact]

---

## 📊 Market Overview

### Asia (Closed)
| Index | Level | Change |
|-------|-------|--------|
| Nikkei 225 | XX,XXX | +X.X% |
| Hang Seng | XX,XXX | +X.X% |
| Shanghai | X,XXX | +X.X% |

### Europe (Live)
| Index | Level | Change |
|-------|-------|--------|
| FTSE 100 | X,XXX | +X.X% |
| DAX | XX,XXX | +X.X% |
| CAC 40 | X,XXX | +X.X% |

### US Futures
| Future | Level | Change |
|--------|-------|--------|
| S&P 500 | X,XXX | +X.X% |
| Nasdaq | XX,XXX | +X.X% |
| VIX | XX.X | +X.X% |

### Commodities & Crypto
| Asset | Price | Change |
|-------|-------|--------|
| Gold | $X,XXX | +X.X% |
| Oil (WTI) | $XX.XX | +X.X% |
| Bitcoin | $XX,XXX | +X.X% |

---

## 🎯 Actionable Summary

**Sentiment:** [Bullish/Bearish/Neutral]

**Top 3 Watch Items:**
1. [Item]
2. [Item]
3. [Item]

**Risk Factors:**
- [Risk]

**Trading Implications:**
- [Implication]
```

---

## Usage

### Manual Run
Ask: "Run morning market intel" or "What's moving globally today?"

### Scheduled (via Heartbeat)
Add to HEARTBEAT.md:
```
## Morning Brief — 7:00 AM PT
Run finance-debrief skill and post to #investment channel
```

### Via Cron
```bash
# 6:30 AM PT daily (before market open)
cron add --schedule "30 6 * * 1-5" --text "Run finance-debrief and post to #investment"
```

---

## Data Freshness

- Always timestamp when data was fetched
- Acknowledge if data is delayed (>15 min)
- Note which markets are open/closed
- Use web search for breaking news

---

## Notes

- Focus on **actionable insights**, not just data dumps
- Keep brief concise (< 500 words for quick scan)
- Flag **urgent items** at the top
- Link to sources when relevant
- This is research/analysis — not trading advice
