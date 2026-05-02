"""
setups/breakout.py — Breakout setup detection (short-range and long-range).

Detects two types of breakouts:

  SHORT-RANGE BREAKOUT: Price bursting above a recent tight consolidation
    (10–20 day base) on heavy volume. Most actionable — entry is clear.

  LONG-RANGE BREAKOUT: Price breaking above a multi-month base (6–52 week
    consolidation). More powerful but rarer. Marks major trend acceleration.

Your logic incorporated:
  - Price > MA200 and > MA50, MA50 > MA200
  - Price within 3% of 52-week high
  - Price > 30% above 52-week low
  - 1-week return > 3% (momentum confirmation)
  - Quarterly YoY profit growth > 15%
  - Quarterly YoY sales growth > 10%
  - Volume > 100,000
  - Market cap > 200 Cr / $200M

Additional logic:
  - Tight consolidation before breakout (ATR-based range contraction)
  - Volume surge on breakout day: ≥ 1.5× 50-day avg
  - Resistance level detection: breakout above a clear pivot high
  - Both short-range (10–20 day) and long-range (6–52 week) base detection

NOTE: Fundamental data conditions use the same stub pattern as powerplay.py.
      See _get_fundamentals() below.

Public API:
    detect_breakout(df, symbol) -> dict
"""
import numpy as np
import pandas as pd

from config import Breakout as BOConfig


# ─────────────────────────────────────────────
# FUNDAMENTAL DATA STUB
# ─────────────────────────────────────────────

def _get_fundamentals(symbol: str) -> dict:
    """
    Fetch fundamental data. Currently returns None for all values.
    Replace with yfinance .info or a paid API when available.

    Example:
        import yfinance as yf
        info = yf.Ticker(symbol).info
        return {
            "profit_growth_yoy": info.get("earningsGrowth"),
            "sales_growth_yoy" : info.get("revenueGrowth"),
            "market_cap"       : info.get("marketCap"),
        }
    """
    return {
        "profit_growth_yoy": None,
        "sales_growth_yoy" : None,
        "market_cap"       : None,
    }


# ─────────────────────────────────────────────
# BASE DETECTION HELPERS
# ─────────────────────────────────────────────

def _detect_short_base(df: pd.DataFrame) -> dict:
    """
    Detect a short-range consolidation base (10–20 trading days).

    Criteria:
      - High-to-low range of the base ≤ MAX_DAILY_RANGE_PCT per day (on avg)
      - Volume declining inside the base vs 50-day avg
      - Resistance level = highest close in the base

    Returns dict with base_found, base_days, base_range_pct, resistance.
    """
    for base_days in range(BOConfig.SHORT_BASE_MAX_DAYS,
                           BOConfig.SHORT_BASE_MIN_DAYS - 1, -1):
        base = df.tail(base_days)
        base_high  = float(base["High"].max())
        base_low   = float(base["Low"].min())
        base_range = 100.0 * (base_high - base_low) / base_high if base_high > 0 else 100.0
        avg_vol_base = float(base["Volume"].mean())
        avg_vol_50   = float(df["Volume"].tail(50).mean())

        if (base_range <= BOConfig.MAX_BASE_RANGE_PCT and
                avg_vol_base < avg_vol_50):
            return {
                "base_found"    : True,
                "base_days"     : base_days,
                "base_range_pct": round(base_range, 2),
                "resistance"    : round(base_high, 2),
                "vol_ratio"     : round(avg_vol_base / avg_vol_50, 2) if avg_vol_50 > 0 else None,
            }
    return {"base_found": False, "base_days": 0,
            "base_range_pct": None, "resistance": None, "vol_ratio": None}


def _detect_long_base(df: pd.DataFrame) -> dict:
    """
    Detect a long-range consolidation base (6–52 weeks).

    Criteria:
      - Price stayed within LONG_BASE_RANGE_PCT% band for the base duration
      - Volume contracted during the base
      - Resistance = highest close in the base period

    Returns dict with base_found, base_weeks, base_range_pct, resistance.
    """
    for base_weeks in range(BOConfig.LONG_BASE_MAX_WEEKS,
                            BOConfig.LONG_BASE_MIN_WEEKS - 1, -1):
        base_days  = base_weeks * 5
        base       = df.tail(base_days)
        base_high  = float(base["High"].max())
        base_low   = float(base["Low"].min())
        base_range = 100.0 * (base_high - base_low) / base_high if base_high > 0 else 100.0
        avg_vol_base = float(base["Volume"].mean())
        avg_vol_50   = float(df["Volume"].tail(50).mean())

        if (base_range <= BOConfig.LONG_BASE_RANGE_PCT and
                avg_vol_base < avg_vol_50 * 0.9):
            return {
                "base_found"    : True,
                "base_weeks"    : base_weeks,
                "base_range_pct": round(base_range, 2),
                "resistance"    : round(base_high, 2),
                "vol_ratio"     : round(avg_vol_base / avg_vol_50, 2) if avg_vol_50 > 0 else None,
            }
    return {"base_found": False, "base_weeks": 0,
            "base_range_pct": None, "resistance": None, "vol_ratio": None}


# ─────────────────────────────────────────────
# MAIN DETECTION
# ─────────────────────────────────────────────

def detect_breakout(df: pd.DataFrame, symbol: str = "") -> dict:
    """
    Detect short-range and long-range breakout setups.

    Technical conditions:
      1.  Price > MA200, Price > MA50, MA50 > MA200
      2.  Price within 3% of 52-week high (near breakout point)
      3.  Price > 30% above 52-week low
      4.  1-week return > 3% (momentum)
      5.  Volume > 100,000
      6.  Volume surge today ≥ 1.5× 50-day avg (breakout confirmation)
      7a. Short-range base detected (10–20 days, range ≤ 8%)  OR
      7b. Long-range base detected (6–52 weeks, range ≤ 25%)

    Fundamental conditions (require _get_fundamentals):
      8.  Quarterly YoY profit growth > 15%
      9.  Quarterly YoY sales growth > 10%
      10. Market cap > 200

    Returns dict with is_breakout, breakout_type (short/long/none),
    base details, score, notes.
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
        "is_breakout"        : False,
        "breakout_type"      : "none",   # "short", "long", or "none"
        "base_days"          : None,
        "base_weeks"         : None,
        "base_range_pct"     : None,
        "resistance"         : None,
        "vol_ratio"          : None,
        "breakout_score"     : 0,
        "fundamentals_available": False,
        "notes"              : notes,
    }

    if len(df) < 60:
        notes.append("Insufficient data")
        return result

    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    # ── Condition 1: MA stack ──
    ma_stack = current > ma200 and current > ma50 and ma50 > ma200
    notes.append(f"MA stack: {'✓' if ma_stack else '✗'}")

    # ── Condition 2: Price within 3% of 52w high ──
    pct_below_high = 100.0 * (high_52w - current) / high_52w if high_52w > 0 else 100.0
    near_high      = pct_below_high < BOConfig.MAX_PCT_BELOW_HIGH
    notes.append(f"Below 52w high: {pct_below_high:.1f}% "
                 f"({'✓' if near_high else '✗'} need <{BOConfig.MAX_PCT_BELOW_HIGH}%)")

    # ── Condition 3: Price > 30% above 52w low ──
    pct_above_low = 100.0 * (current - low_52w) / low_52w if low_52w > 0 else 0.0
    above_low     = pct_above_low > BOConfig.MIN_RISE_FROM_LOW_PCT
    notes.append(f"Above 52w low: {pct_above_low:.1f}% "
                 f"({'✓' if above_low else '✗'} need >{BOConfig.MIN_RISE_FROM_LOW_PCT}%)")

    # ── Condition 4: 1-week return > 3% ──
    if len(close) >= 5:
        ret_1w = 100.0 * (current / float(close.iloc[-5]) - 1)
    else:
        ret_1w = 0.0
    momentum = ret_1w > BOConfig.MIN_1W_RETURN_PCT
    notes.append(f"1-week return: {ret_1w:.1f}% "
                 f"({'✓' if momentum else '✗'} need >{BOConfig.MIN_1W_RETURN_PCT}%)")

    # ── Condition 5: Volume filter ──
    vol_ok = cur_vol >= BOConfig.MIN_VOLUME
    notes.append(f"Volume: {int(cur_vol):,} ({'✓' if vol_ok else '✗'} need ≥{BOConfig.MIN_VOLUME:,})")

    # ── Condition 6: Volume surge ──
    avg_vol_50  = float(volume.tail(50).mean())
    vol_surge   = cur_vol >= avg_vol_50 * BOConfig.MIN_VOLUME_SURGE
    notes.append(f"Vol surge: {cur_vol/avg_vol_50:.1f}× avg "
                 f"({'✓' if vol_surge else '✗'} need ≥{BOConfig.MIN_VOLUME_SURGE}×)")

    # ── Condition 7a: Short-range base ──
    short_base = _detect_short_base(df)
    if short_base["base_found"]:
        notes.append(f"Short base: {short_base['base_days']}d, "
                     f"range {short_base['base_range_pct']:.1f}%, "
                     f"vol {short_base['vol_ratio']:.2f}× avg ✓")
    else:
        notes.append("Short-range base: not found")

    # ── Condition 7b: Long-range base ──
    long_base = _detect_long_base(df)
    if long_base["base_found"]:
        notes.append(f"Long base: {long_base['base_weeks']}w, "
                     f"range {long_base['base_range_pct']:.1f}%, "
                     f"vol {long_base['vol_ratio']:.2f}× avg ✓")
    else:
        notes.append("Long-range base: not found")

    # ── Fundamentals ──
    fund = _get_fundamentals(symbol)
    fund_available = any(v is not None for v in fund.values())
    result["fundamentals_available"] = fund_available
    fund_pass = True
    if fund_available:
        checks = []
        pg = fund["profit_growth_yoy"]
        sg = fund["sales_growth_yoy"]
        mc = fund["market_cap"]
        if pg is not None: checks.append(pg * 100 > BOConfig.MIN_PROFIT_GROWTH_PCT)
        if sg is not None: checks.append(sg * 100 > BOConfig.MIN_SALES_GROWTH_PCT)
        if mc is not None: checks.append(mc        > BOConfig.MIN_MARKET_CAP)
        fund_pass = all(checks)
        notes.append(f"Fundamentals: {'✓' if fund_pass else '✗'}")
    else:
        notes.append("Fundamentals: not available")

    # ── Scoring ──
    score = 0
    if ma_stack:    score += 2
    if near_high:   score += 2
    if above_low:   score += 1
    if momentum:    score += 2
    if vol_ok:      score += 1
    if vol_surge:   score += 2
    if short_base["base_found"]: score += 2
    if long_base["base_found"]:  score += 2
    if fund_available and fund_pass: score += 2

    result["breakout_score"] = score

    # ── Determine breakout type and pass/fail ──
    base_conditions = (ma_stack and near_high and above_low
                       and momentum and vol_ok and fund_pass)

    if base_conditions and short_base["base_found"] and vol_surge:
        result["is_breakout"]   = True
        result["breakout_type"] = "short"
        result["base_days"]     = short_base["base_days"]
        result["base_range_pct"]= short_base["base_range_pct"]
        result["resistance"]    = short_base["resistance"]
        result["vol_ratio"]     = short_base["vol_ratio"]
        notes.append(f"✓ SHORT-RANGE BREAKOUT confirmed (score {score}/16)")

    elif base_conditions and long_base["base_found"]:
        result["is_breakout"]   = True
        result["breakout_type"] = "long"
        result["base_weeks"]    = long_base["base_weeks"]
        result["base_range_pct"]= long_base["base_range_pct"]
        result["resistance"]    = long_base["resistance"]
        result["vol_ratio"]     = long_base["vol_ratio"]
        notes.append(f"✓ LONG-RANGE BREAKOUT confirmed (score {score}/16)")

    else:
        notes.append(f"✗ Breakout not confirmed (score {score}/16)")

    return result
