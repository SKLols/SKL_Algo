"""
setups/powerplay.py — Minervini Power Play setup detection.

A Power Play is a strong momentum setup where a stock that has already
made a big prior move is now consolidating near its highs and showing
explosive single-day or multi-day power moves on above-average volume,
combined with strong fundamentals.

Your logic incorporated:
  - Price > MA200 and > MA50, MA50 > MA200
  - 1-year return > 100%
  - Price within 1–10% of 52-week high
  - Price > 100% above 52-week low
  - Quarterly YoY profit growth > 25%
  - Quarterly YoY sales growth > 20%
  - ROE > 15%
  - Debt/Equity < 1
  - Volume > 100,000
  - Market cap > 500 Cr / $500M

Additional logic added:
  - Recent power day: single day gain ≥ 0.75% on volume ≥ 1.25× 50-day avg
  - Price tightening: last 10 days range ≤ 5% (coiling before next move)
  - Momentum: price above EMA10 and EMA20

NOTE: Fundamental data (profit growth, sales growth, ROE, D/E, market cap)
      is NOT available from yfinance OHLCV data. These conditions are flagged
      as "requires fundamental data" and set to None in the result dict.
      To enable them, integrate a fundamental data provider (e.g. yfinance
      .info dict, or a paid API like Screener.in / Financial Modelling Prep).
      A helper stub _get_fundamentals() is provided for easy integration.

Public API:
    detect_powerplay(df, symbol) -> dict
"""
import numpy as np
import pandas as pd

from config import PowerPlay as PPConfig


# ─────────────────────────────────────────────
# FUNDAMENTAL DATA STUB
# ─────────────────────────────────────────────

def _get_fundamentals(symbol: str) -> dict:
    """
    Fetch fundamental data for a symbol.

    CURRENTLY RETURNS None FOR ALL VALUES.
    To enable: replace the body with a yfinance .info call or API call.

    Example with yfinance:
        import yfinance as yf
        info = yf.Ticker(symbol).info
        return {
            "profit_growth_yoy" : info.get("earningsGrowth"),       # decimal e.g. 0.30
            "sales_growth_yoy"  : info.get("revenueGrowth"),        # decimal
            "roe"               : info.get("returnOnEquity"),        # decimal
            "debt_to_equity"    : info.get("debtToEquity"),          # ratio
            "market_cap"        : info.get("marketCap"),             # absolute value
        }
    """
    return {
        "profit_growth_yoy" : None,   # fill with actual data when available
        "sales_growth_yoy"  : None,
        "roe"               : None,
        "debt_to_equity"    : None,
        "market_cap"        : None,
    }


# ─────────────────────────────────────────────
# MAIN DETECTION
# ─────────────────────────────────────────────

def detect_powerplay(df: pd.DataFrame, symbol: str = "") -> dict:
    """
    Detect a Minervini Power Play setup.

    Technical conditions (evaluated from OHLCV):
      1.  Price > MA200, Price > MA50, MA50 > MA200
      2.  1-year return > 100%
      3.  Price within 1–10% of 52-week high
      4.  Price > 100% above 52-week low
      5.  Volume > 100,000
      6.  Recent power day: single-day gain ≥ 0.75% on ≥ 1.25× avg volume
      7.  Price tightening last 10 days (range ≤ 5% of price)
      8.  Price above EMA10 and EMA20 (short-term momentum)

    Fundamental conditions (require external data — see _get_fundamentals):
      9.  Quarterly YoY profit growth > 25%
      10. Quarterly YoY sales growth > 20%
      11. ROE > 15%
      12. Debt/Equity < 1
      13. Market cap > 500 (Cr or $M depending on market)

    Returns dict with is_powerplay, score, fundamentals_available flag, notes.
    """
    close  = df["Close"]
    high   = df["High"]
    low    = df["Low"]
    volume = df["Volume"]

    current  = float(close.iloc[-1])
    cur_vol  = float(volume.iloc[-1])
    high_52w = float(high.tail(252).max())
    low_52w  = float(low.tail(252).min())

    notes = []

    result = {
        "is_powerplay"           : False,
        "powerplay_score"        : 0,
        "fundamentals_available" : False,
        "profit_growth_yoy"      : None,
        "sales_growth_yoy"       : None,
        "roe"                    : None,
        "debt_to_equity"         : None,
        "market_cap"             : None,
        "notes"                  : notes,
    }

    if len(df) < 60:
        notes.append("Insufficient data")
        return result

    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    # ── Condition 1: MA stack ──
    ma_stack = current > ma200 and current > ma50 and ma50 > ma200
    notes.append(f"MA stack (Price>MA50>MA200): {'✓' if ma_stack else '✗'}")

    # ── Condition 2: 1-year return > 100% ──
    if len(close) >= 252:
        ret_1y = 100.0 * (current / float(close.iloc[-252]) - 1)
    else:
        ret_1y = 100.0 * (current / float(close.iloc[0]) - 1)
    ret_ok = ret_1y > PPConfig.MIN_1Y_RETURN_PCT
    notes.append(f"1-year return: {ret_1y:.1f}% "
                 f"({'✓' if ret_ok else '✗'} need >{PPConfig.MIN_1Y_RETURN_PCT}%)")

    # ── Condition 3: Price within 1–10% of 52w high ──
    pct_below_high = 100.0 * (high_52w - current) / high_52w if high_52w > 0 else 100.0
    near_high = PPConfig.MIN_PCT_BELOW_HIGH < pct_below_high < PPConfig.MAX_PCT_BELOW_HIGH
    notes.append(f"Below 52w high: {pct_below_high:.1f}% "
                 f"({'✓' if near_high else '✗'} need {PPConfig.MIN_PCT_BELOW_HIGH}–{PPConfig.MAX_PCT_BELOW_HIGH}%)")

    # ── Condition 4: Price > 100% above 52w low ──
    pct_above_low  = 100.0 * (current - low_52w) / low_52w if low_52w > 0 else 0.0
    strong_move    = pct_above_low > PPConfig.MIN_RISE_FROM_LOW_PCT
    notes.append(f"Above 52w low: {pct_above_low:.1f}% "
                 f"({'✓' if strong_move else '✗'} need >{PPConfig.MIN_RISE_FROM_LOW_PCT}%)")

    # ── Condition 5: Volume ──
    vol_ok = cur_vol >= PPConfig.MIN_VOLUME
    notes.append(f"Volume: {int(cur_vol):,} ({'✓' if vol_ok else '✗'} need ≥{PPConfig.MIN_VOLUME:,})")

    # ── Condition 6: Recent power day ──
    avg_vol_50  = float(volume.tail(50).mean())
    power_day   = False
    power_bars  = df.tail(PPConfig.LOOKBACK_DAYS).copy()
    for i in range(1, len(power_bars)):
        day_gain = 100.0 * (float(power_bars["Close"].iloc[i]) /
                             float(power_bars["Close"].iloc[i - 1]) - 1)
        day_vol  = float(power_bars["Volume"].iloc[i])
        if day_gain >= PPConfig.MIN_SINGLE_DAY_GAIN_PCT and \
           day_vol  >= avg_vol_50 * PPConfig.MIN_POWER_DAY_VOLUME:
            power_day = True
            notes.append(f"Power day found: +{day_gain:.2f}% on "
                         f"{day_vol/avg_vol_50:.1f}× avg vol ✓")
            break
    if not power_day:
        notes.append(f"No power day in last {PPConfig.LOOKBACK_DAYS} sessions ✗")

    # ── Condition 7: Price tightening last 10 days ──
    last10       = df.tail(10)
    range10_pct  = 100.0 * (float(last10["High"].max()) - float(last10["Low"].min())) / current
    tight_10d    = range10_pct <= PPConfig.MAX_10D_RANGE_PCT
    notes.append(f"10-day range: {range10_pct:.1f}% "
                 f"({'✓ tight' if tight_10d else '✗ too wide'} need ≤{PPConfig.MAX_10D_RANGE_PCT}%)")

    # ── Condition 8: Above EMA10 and EMA20 ──
    ema10_ok = ema20_ok = False
    if "EMA_10" in df.columns and "EMA_20" in df.columns:
        ema10_ok = current > float(df["EMA_10"].iloc[-1])
        ema20_ok = current > float(df["EMA_20"].iloc[-1])
        notes.append(f"Above EMA10: {'✓' if ema10_ok else '✗'}  "
                     f"Above EMA20: {'✓' if ema20_ok else '✗'}")

    # ── Fundamentals (optional — see _get_fundamentals stub) ──
    fund = _get_fundamentals(symbol)
    fundamentals_available = any(v is not None for v in fund.values())
    result["fundamentals_available"] = fundamentals_available
    result["profit_growth_yoy"]      = fund["profit_growth_yoy"]
    result["sales_growth_yoy"]       = fund["sales_growth_yoy"]
    result["roe"]                    = fund["roe"]
    result["debt_to_equity"]         = fund["debt_to_equity"]
    result["market_cap"]             = fund["market_cap"]

    fund_pass = True   # default pass when data unavailable
    if fundamentals_available:
        pg  = fund["profit_growth_yoy"]
        sg  = fund["sales_growth_yoy"]
        roe = fund["roe"]
        de  = fund["debt_to_equity"]
        mc  = fund["market_cap"]
        checks = []
        if pg  is not None: checks.append(pg  * 100 > PPConfig.MIN_PROFIT_GROWTH_PCT)
        if sg  is not None: checks.append(sg  * 100 > PPConfig.MIN_SALES_GROWTH_PCT)
        if roe is not None: checks.append(roe * 100 > PPConfig.MIN_ROE_PCT)
        if de  is not None: checks.append(de        < PPConfig.MAX_DEBT_EQUITY)
        if mc  is not None: checks.append(mc        > PPConfig.MIN_MARKET_CAP)
        fund_pass = all(checks)
        notes.append(f"Fundamentals: {'✓ pass' if fund_pass else '✗ fail'}")
    else:
        notes.append("Fundamentals: not available (enable _get_fundamentals)")

    # ── Scoring ──
    score = 0
    if ma_stack:    score += 2
    if ret_ok:      score += 2
    if near_high:   score += 2
    if strong_move: score += 1
    if vol_ok:      score += 1
    if power_day:   score += 2
    if tight_10d:   score += 1
    if ema10_ok and ema20_ok: score += 1
    if fundamentals_available and fund_pass: score += 2

    result["powerplay_score"] = score

    # ── Pass / fail ──
    tech_pass = (ma_stack and ret_ok and near_high and strong_move
                 and vol_ok and power_day)
    if tech_pass and fund_pass:
        result["is_powerplay"] = True
        notes.append(f"✓ POWER PLAY setup confirmed (score {score}/14)")
    else:
        notes.append(f"✗ Power Play not confirmed (score {score}/14)")

    return result
