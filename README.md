# SKL_Algo — Minervini Stock Scanner

A modular Python scanner that detects high-probability trading setups based on **Mark Minervini's** methodology — Trend Template, VCP (Volatility Contraction Pattern), and more.

Works with **NSE (India)** and **US (S&P 500)** stocks via free `yfinance` data. Optional **Telegram integration** sends automated scan results to your phone every morning and evening.

---

## Features

- Minervini's 8-condition **Trend Template** (Stage 2 uptrend filter)
- **VCP** — Volatility Contraction Pattern with candle-level nesting (Grade A / B / C / D)
- **Darvas Box** — consolidation box detection with volume compression and breakout confirmation
- **Power Play** — explosive momentum days near 52-week highs after a strong prior move
- **Breakout** — short-range (10–20 day) and long-range (6–52 week) base breakouts with volume surge
- **Cup & Handle** — U-shaped base (7–65 weeks) with tight handle and pivot breakout
- **Relative Strength** vs Nifty 50 or S&P 500
- **Volume dry-up** detection on final contraction
- **Dark-theme charts** — candlestick + EMA + swing markers + contraction bands + pivot line
- **Market Breadth** — standalone check of how many stocks are in Stage 2
- **Excel export** of all valid setups (all setup types in one file)
- **Telegram alerts** — automated daily scans sent to your Telegram chat
- **Windows Task Scheduler** support — run scans automatically without keeping Python open

---

## Project Structure

```
scanner/
├── config.py                   ← All tunable constants (edit this, not other files)
├── scanner.py                  ← Main entry point — runs VCP scan
├── market_breadth.py           ← Standalone market health check
│
├── scheduler.py                ← Automated daily scans + Telegram notifications
├── setup_scheduler.py          ← One-time Windows Task Scheduler registration
├── telegram_notifier.py        ← Telegram messaging logic (formatting, upload)
├── telegram_config.py          ← YOUR credentials (git-ignored — see setup below)
├── telegram_config.example.py  ← Template — copy this to create telegram_config.py
│
├── data/
│   ├── universe.py             ← Stock list loaders (NSE500, SP500, custom)
│   └── fetcher.py              ← yfinance download, benchmark cache, RS, EMAs
│
├── indicators/
│   ├── trend_template.py       ← Minervini's 8-condition Stage 2 filter
│   └── swings.py               ← Swing high/low detection on close price
│
├── setups/
│   ├── vcp.py                  ← Volatility Contraction Pattern (Grade A/B/C/D)
│   ├── breakout.py             ← Short-range (10–20d) and long-range (6–52w) breakouts
│   ├── darvas.py               ← Darvas Box consolidation + volume compression
│   ├── powerplay.py            ← Power Play — explosive move near highs after big prior run
│   └── cup_handle.py           ← Cup & Handle — U-shaped base with tight handle
│
└── output/
    ├── charts.py               ← Candlestick chart generation (mplfinance)
    ├── console.py              ← Terminal print functions
    └── exporter.py             ← Excel / CSV export
```

Output is written to `./output/` (inside `scanner/`):
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
cd SKL_Algo/scanner

# 2. Create and activate a virtual conda environment (recommended)
conda create --name algo_trading python=3.10 -y
conda activate algo_trading

# 3. Install dependencies
pip install -r requirements.txt
```

---

## How to Run

All commands are run from inside the `scanner/` folder.

### Run the VCP scanner
```bash
python scanner.py
```
Scans the active universe, prints results to terminal, saves charts to `output/charts/`, and saves Excel to `output/vcp_scan_results.xlsx`.

### Run the market breadth check
```bash
python market_breadth.py
```
Checks how many stocks in the universe pass the Trend Template. Run this first every morning — if fewer than 40% of stocks pass, setups have lower probability.

---

## Telegram Alerts Setup

> `telegram_config.py` is **git-ignored** and must be created locally. Never commit it — it contains your private bot token.

### Step 1 — Create your Telegram bot

1. Open Telegram and message **@BotFather**
2. Send `/newbot` and follow the prompts
3. Copy the **bot token** (looks like `123456789:ABCdef...`)

### Step 2 — Get your chat ID

1. Message **@userinfobot** on Telegram
2. Copy the **id** number it sends back (e.g. `379053967`)

### Step 3 — Create your config file

```bash
cp telegram_config.example.py telegram_config.py
```

Edit `telegram_config.py` and replace the placeholders:

```python
TELEGRAM_BOT_TOKEN = "123456789:ABCdef..."   # from @BotFather
TELEGRAM_CHAT_ID   = "379053967"             # from @userinfobot
```

### Step 4 — Test the connection

```bash
python scheduler.py --test
```

You should receive a test message in Telegram.

### Step 5 — Run the scheduler

**Option A — Keep running in the terminal** (stays open while you run it):
```bash
python scheduler.py
```
Scans automatically at market open (6:00 AM CET) and market close (11:00 AM CET). Send `/run_manual` to your bot anytime to trigger an immediate scan.

**Option B — Windows Task Scheduler** (runs silently in the background, no terminal needed):
```bash
python setup_scheduler.py
```
This registers two Windows Task Scheduler jobs (`VCP Scanner - Market Open` and `VCP Scanner - Market Close`) that fire daily at the configured times. Verify them in the Windows Task Scheduler app.

**Option C — Run once manually**:
```bash
python scheduler.py --run-once open    # simulate market open scan
python scheduler.py --run-once close   # simulate market close scan
```

### Telegram timing (Indian market / Germany timezone)

| Event | Germany time | India time (IST) |
|-------|-------------|-----------------|
| Market open scan | 6:00 AM CET / 7:00 AM CEST | ~9:45 AM IST |
| Market close scan | 11:00 AM CET / 12:00 PM CEST | ~3:00 PM IST |

Times are set in `telegram_config.py` under `MARKET_OPEN_TIME` and `MARKET_CLOSE_TIME`. `pytz` handles daylight saving time automatically.

---

## Configuration

**Everything you need to change is in `config.py` — never edit any other file for configuration.**

### Switch between markets

```python
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
    LOOKBACK_DAYS  = 180     # days of candles shown on chart
    DPI            = 130     # resolution — lower for faster generation
    SAVE_ALL_GRADES = True   # False = Grade A charts only
```

### Telegram alert filters (in `telegram_config.py`)

```python
SETUP_GRADES = ["A", "B"]          # which grades to include in reports
NOTIFY_ON_VALID_SETUPS_ONLY = True  # only notify when setups exist (no empty scans)
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

All existing setups (VCP, Darvas, Power Play, Breakout, Cup & Handle) follow the same pattern — **only 3 files need to change**:

### Step 1 — `config.py`
Add a config class with all parameters for the new setup.

### Step 2 — Create `setups/mysetup.py`

```python
from config import MySetup as MSConfig

def detect_mysetup(df, symbol="") -> dict:
    # detection logic here
    # return dict with is_mysetup, score, notes, etc.
    ...
```

### Step 3 — `scanner.py` — add 4 lines

```python
# Import at the top:
from setups.mysetup import detect_mysetup

# In scan_stock(), run detection:
ms = detect_mysetup(df, symbol=symbol)
if not trend["all_pass"]:
    ms["is_mysetup"] = False

# Add to the returned dict:
"is_mysetup"   : ms["is_mysetup"],
"mysetup_score": ms.get("score"),
"mysetup_notes": ms.get("notes"),
```

Console, Excel, and chart modules need no changes until you want setup-specific annotations.

---

## Setup Scoring

Each setup returns a numeric score so you can rank results:

| Setup | Max Score | Key Conditions |
|-------|-----------|----------------|
| VCP | 11 pts | Nesting (C3→C2→C1), tight final contraction, volume dry-up |
| Darvas Box | 12 pts | Near 52w high, box weeks/tightness, volume compression |
| Power Play | 14 pts | MA stack, 1-year return >100%, power day, 10-day coil |
| Breakout | 16 pts | MA stack, near high, momentum, volume surge, base type |
| Cup & Handle | 17 pts | MA stack, cup geometry, handle retrace, volume contraction |

Fundamental data (profit/sales growth, ROE, D/E) is stubbed out with `None` in `_get_fundamentals()` inside each setup file. To enable it, replace the stub with a `yfinance .info` call or a paid API.

---

## Roadmap

- [x] VCP (Volatility Contraction Pattern)
- [x] Darvas Box
- [x] Power Play setup
- [x] Breakout from tight range (short + long base)
- [x] Cup & Handle
- [x] Market Breadth (Trend Template count)
- [x] Telegram alerts (automated daily scans)
- [x] Windows Task Scheduler integration
- [ ] Fundamental data integration (yfinance .info or paid API)
- [ ] Parallel scanning (`concurrent.futures`) for faster runs
- [ ] Backtest mode — validate Grade A setups historically

---

## Disclaimer

This tool is for **educational and research purposes only**. Nothing here constitutes financial advice. Always do your own analysis before making any trading decisions.

---

## Credits

Setup logic based on **Mark Minervini's** *Trade Like a Stock Market Wizard* and *Think & Trade Like a Champion*.
