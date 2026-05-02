# SKL_Algo
# Minervini Stock Scanner

A modular Python scanner that detects high-probability trading setups based on **Mark Minervini's** methodology — Trend Template, VCP (Volatility Contraction Pattern), and more.

Works with **NSE (India)** and **US (S&P 500)** stocks via free `yfinance` data.

---

## Features

- ✅ Minervini's 8-condition **Trend Template** (Stage 2 uptrend filter)
- ✅ **VCP detection** with candle-level nesting validation (Grade A / B / C / D)
- ✅ **Relative Strength** vs Nifty 50 or S&P 500
- ✅ **Volume dry-up** detection on final contraction
- ✅ **Dark-theme charts** — candlestick + EMA + swing markers + contraction bands + pivot line
- ✅ **Market Breadth** — standalone check of how many stocks are in Stage 2
- ✅ **Excel export** of all valid setups
- ✅ Modular structure — add new setups (Darvas, Breakout, Cup & Handle) with minimal changes

---

## Project Structure

```
scanner/
├── config.py               ← All tunable constants (edit this, nothing else)
├── scanner.py              ← Main entry point — runs VCP scan
├── market_breadth.py       ← Standalone market health check
│
├── data/
│   ├── universe.py         ← Stock list loaders (NSE500, SP500, custom)
│   └── fetcher.py          ← yfinance download, benchmark cache, RS, EMAs
│
├── indicators/
│   ├── trend_template.py   ← Minervini's 8-condition Stage 2 filter
│   └── swings.py           ← Swing high/low detection on close price
│
├── setups/
│   ├── vcp.py              ← Volatility Contraction Pattern
│   ├── breakout.py         ← (coming) Breakout from tight range
│   ├── darvas.py           ← (coming) Darvas Box
│   ├── powerplay.py        ← (coming) Power Play setup
│   └── cup_handle.py       ← (coming) Cup & Handle
│
└── output/
    ├── charts.py           ← Candlestick chart generation (mplfinance)
    ├── console.py          ← Terminal print functions
    └── exporter.py         ← Excel / CSV export
```

Output is written to `../output/` (one level above `scanner/`):
```
output/
├── vcp_scan_results.xlsx
├── market_breadth.xlsx
└── charts/
    ├── A_NVDA_9pts.png
    ├── B_AAPL_7pts.png
    └── ...
```

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/SKLols/SKL_Algo.git
cd SKL_Algo

# 2. Create and activate a virtual conda environment (recommended)
conda create --name algo_trading python=3.10 -y
conda activate algo_trading         # Windows

# 3. Install dependencies
pip install -r requirements.txt
#OR
pip install yfinance pandas numpy mplfinance matplotlib openpyxl
```

---

## How to Run

All commands are run from **inside the `scanner/` folder**:

```bash
cd scanner
```

### Run the VCP scanner
```bash
python scanner.py
```
Scans the active universe, prints results to terminal, saves charts to `output/charts/`, saves Excel to `output/vcp_scan_results.xlsx`.

### Run the market breadth check
```bash
python market_breadth.py
```
Checks how many stocks in the universe pass the Trend Template. Run this first every morning — if the market is in poor condition (< 40% stocks passing), setups are lower probability.

---

## Configuration

**Everything you need to change is in `config.py` — never edit any other file for configuration.**

### Switch between markets

```python
# config.py
class Universe:
    ACTIVE = "SP500"    # ← change to "NSE500" or "CUSTOM"
```

### Scan a custom watchlist

```python
class Universe:
    ACTIVE = "CUSTOM"
    CUSTOM_SYMBOLS = [
        "RELIANCE.NS",
        "INFY.NS",
        "AAPL",
        "NVDA",
    ]
```

### Tune VCP parameters

```python
class VCP:
    MIN_CONTRACTIONS      = 2      # raise to 3 for stricter setups
    MAX_FINAL_CONTRACTION = 10.0   # lower to 7.0 for tighter final squeeze
    MIN_VOLUME_DRY_UP     = 0.9    # lower = stricter volume dry-up requirement
```

### Tune Trend Template thresholds

```python
class TrendTemplate:
    PCT_ABOVE_52W_LOW  = 30.0   # Minervini default — raise for stronger uptrends
    PCT_BELOW_52W_HIGH = 25.0   # Minervini default — lower to scan near-highs only
```

### Chart appearance

```python
class Chart:
    LOOKBACK_DAYS = 180      # days of candles shown on chart
    DPI           = 130      # resolution — lower for faster generation
    SAVE_ALL_GRADES = True   # False = Grade A charts only
```

---

## Understanding the Output

### VCP Grades

| Grade | Meaning |
|-------|---------|
| **A** | C3 nested inside C2 nested inside C1 — textbook VCP |
| **B** | Latest 2 contractions validly nested |
| **C** | Previous 2 of last 3 validly nested |
| **D** | Nesting structure valid but final contraction too wide |

### VCP Score (0–11)

| Condition | Points |
|-----------|--------|
| 3-step nested structure (C3 in C2 in C1) | 4 |
| 2-step nested structure | 2 |
| Final contraction ≤ 10% | 2 |
| Volume dry-up confirmed | 2 |
| Volume declining across contractions | 1 |
| 3+ contractions found | 1 |
| Price within 5% of 52-week high | 1 |

### Chart annotations

- **▼ red** markers = swing highs detected on close price
- **▲ green** markers = swing lows detected on close price
- **Shaded bands** = each contraction (C1, C2, C3…) — visually narrows right to left
- **Yellow dashed line** = pivot breakout price (buy trigger)
- **Volume panel** = highlighted in the final contraction window when dry-up confirmed

---

## Adding a New Setup

Adding Darvas Box as an example — **only 3 files change**:

### Step 1 — `config.py` (already done)
The `Darvas` class with all parameters is already there. Tune the values.

### Step 2 — Create `setups/darvas.py`

```python
from config import Darvas as DarvasConfig
from indicators.swings import build_alternating_swings

def detect_darvas(df) -> dict:
    # your detection logic here
    # return dict with is_darvas, box_top, box_bottom, notes, etc.
    ...
```

### Step 3 — `scanner.py` — add 3 lines

```python
# At the top with other imports:
from setups.darvas import detect_darvas

# Inside scan_stock(), after the VCP block:
darvas = detect_darvas(df)
if not trend["all_pass"]:
    darvas["is_darvas"] = False

# Add to the returned dict:
"is_darvas"   : darvas["is_darvas"],
"darvas_notes": darvas["notes"],
```

That's it. Console, Excel, and chart modules need no changes until you want Darvas-specific chart annotations.

---

## Roadmap

- [x] VCP (Volatility Contraction Pattern)
- [x] Market Breadth (Trend Template count)
- [ ] Breakout from tight range
- [ ] Darvas Box
- [ ] Power Play setup
- [ ] Cup & Handle
- [ ] Parallel scanning (`concurrent.futures`) for faster runs
- [ ] Backtest mode — validate Grade A setups historically

---

## Disclaimer

This tool is for **educational and research purposes only**. Nothing here constitutes financial advice. Always do your own analysis before making any trading decisions.

---

## Credits

Setup logic based on **Mark Minervini's** *Trade Like a Stock Market Wizard* and *Think & Trade Like a Champion*.