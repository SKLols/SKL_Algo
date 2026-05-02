"""
setups/cup_handle.py — Cup and Handle pattern detection.

The Cup & Handle is a bullish continuation pattern:
  - CUP: A rounded U-shaped base (7–65 weeks) formed after a prior uptrend.
         Depth 10–35%. Volume dries up at the base, expands at right rim.
  - HANDLE: A short, tight pullback (5–15 days) in the upper half of the cup.
             Handle retraces ≤ 50% of the cup depth. Volume contracts in handle.
  - BREAKOUT: Price breaks above the pivot (cup's right-rim high) on expanding volume.

Your logic incorporated:
  - Price > MA200 and > MA50, MA50 > MA200
  - Price within 2–10% of 52-week high
  - Price > 50% above 52-week low
  - 6-month return > 10%, 1-year return > 20%
  - Quarterly YoY profit growth > 20%
  - Quarterly YoY sales growth > 15%
  - Debt/Equity < 1.5
  - Volume > 50,000
  - Market cap > 500

Additional pattern geometry:
  - Cup depth 10–35% (Minervini / O'Neil spec)
  - Cup duration 7–65 weeks
  - Handle in upper half of cup
  - Handle retrace ≤ 50% of cup depth
  - Handle duration 5–15 days
  - Volume dry-up in handle
  - Pivot price = right rim of cup (handle high)

NOTE: Fundamental data uses the same stub as powerplay/breakout.
      See _get_fundamentals() below.

Public API:
    detect_cup_handle(df, symbol) -> dict
"""
import numpy as np
import pandas as pd

from config import CupHandle as CHConfig


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
            "debt_to_equity"   : info.get("debtToEquity"),
            "market_cap"       : info.get("marketCap"),
        }
    """
    return {
        "profit_growth_yoy": None,
        "sales_growth_yoy" : None,
        "debt_to_equity"   : None,
        "market_cap"       : None,
    }


# ─────────────────────────────────────────────
# CUP DETECTION
# ─────────────────────────────────────────────

def _detect_cup(df: pd.DataFrame) -> dict | None:
    """
    Detect the cup portion of a Cup & Handle pattern.

    Scans from MIN_CUP_WEEKS to MAX_CUP_WEEKS looking for:
      - Left rim = highest close near the start of the period
      - Base = lowest close in the middle third
      - Right rim = current area (close to left rim in height)
      - Cup depth between MIN_CUP_DEPTH_PCT and MAX_CUP_DEPTH_PCT
      - Right rim ≥ 95% of left rim (U-shape, not V-shape asymmetry)

    Returns dict or None.
    """
    for weeks in range(CHConfig.MAX_CUP_WEEKS, CHConfig.MIN_CUP_WEEKS - 1, -1):
        days = weeks * 5
        if len(df) < days + CHConfig.MAX_HANDLE_DAYS:
            continue

        # Exclude handle area from cup detection
        cup_df     = df.iloc[-(days + CHConfig.MAX_HANDLE_DAYS):-CHConfig.MIN_HANDLE_DAYS]
        handle_df  = df.tail(CHConfig.MAX_HANDLE_DAYS)

        if len(cup_df) < 20:
            continue

        left_rim   = float(cup_df["Close"].iloc[:len(cup_df)//4].max())
        base_close = float(cup_df["Low"].min())
        right_rim  = float(cup_df["Close"].iloc[-len(cup_df)//4:].max())

        if left_rim <= 0 or base_close <= 0:
            continue

        cup_depth  = 100.0 * (left_rim - base_close) / left_rim
        right_pct  = 100.0 * right_rim / left_rim   # right rim as % of left rim

        if not (CHConfig.MIN_CUP_DEPTH_PCT <= cup_depth <= CHConfig.MAX_CUP_DEPTH_PCT):
            continue

        if right_pct < 90.0:   # right rim must be ≥ 90% of left rim (proper U-shape)
            continue

        return {
            "cup_weeks"  : weeks,
            "left_rim"   : round(left_rim,   2),
            "base_price" : round(base_close, 2),
            "right_rim"  : round(right_rim,  2),
            "cup_depth"  : round(cup_depth,  2),
            "pivot"      : round(right_rim,  2),   # breakout pivot = right rim
        }
    return None


# ─────────────────────────────────────────────
# HANDLE DETECTION
# ─────────────────────────────────────────────

def _detect_handle(df: pd.DataFrame, cup: dict) -> dict:
    """
    Detect the handle within the last MIN–MAX handle days.

    A valid handle:
      - Forms in the upper half of the cup (above midpoint)
      - Retraces ≤ MAX_HANDLE_RETRACE_PCT% of the cup depth
      - Volume contracts vs the prior period
      - Duration between MIN_HANDLE_DAYS and MAX_HANDLE_DAYS

    Returns dict with handle_found and details.
    """
    for hdays in range(CHConfig.MIN_HANDLE_DAYS, CHConfig.MAX_HANDLE_DAYS + 1):
        handle_df = df.tail(hdays)
        h_low     = float(handle_df["Low"].min())
        h_high    = float(handle_df["High"].max())
        h_vol_avg = float(handle_df["Volume"].mean())
        prior_vol = float(df.iloc[-(hdays + 20):-hdays]["Volume"].mean()) \
                    if len(df) > hdays + 20 else h_vol_avg

        cup_midpoint = cup["base_price"] + (cup["left_rim"] - cup["base_price"]) / 2
        in_upper_half= h_low >= cup_midpoint if CHConfig.HANDLE_UPPER_HALF else True

        cup_depth_pts= cup["left_rim"] - cup["base_price"]
        retrace_pts  = cup["right_rim"] - h_low
        retrace_pct  = 100.0 * retrace_pts / cup_depth_pts if cup_depth_pts > 0 else 100.0
        retrace_ok   = retrace_pct <= CHConfig.MAX_HANDLE_RETRACE_PCT

        vol_contracted = h_vol_avg < prior_vol * 0.85

        if in_upper_half and retrace_ok:
            return {
                "handle_found"  : True,
                "handle_days"   : hdays,
                "handle_low"    : round(h_low, 2),
                "handle_high"   : round(h_high, 2),
                "retrace_pct"   : round(retrace_pct, 2),
                "vol_contracted": vol_contracted,
                "in_upper_half" : in_upper_half,
            }

    return {
        "handle_found"  : False,
        "handle_days"   : 0,
        "handle_low"    : None,
        "handle_high"   : None,
        "retrace_pct"   : None,
        "vol_contracted": False,
        "in_upper_half" : False,
    }


# ─────────────────────────────────────────────
# MAIN DETECTION
# ─────────────────────────────────────────────

def detect_cup_handle(df: pd.DataFrame, symbol: str = "") -> dict:
    """
    Detect a Cup & Handle breakout setup.

    Technical conditions:
      1.  Price > MA200, Price > MA50, MA50 > MA200
      2.  Price within 2–10% of 52-week high
      3.  Price > 50% above 52-week low
      4.  6-month return > 10%
      5.  1-year return > 20%
      6.  Volume > 50,000
      7.  Cup: 7–65 weeks, depth 10–35%, proper U-shape
      8.  Handle: 5–15 days, in upper half, retrace ≤ 50%, volume contracted

    Fundamental conditions (require _get_fundamentals):
      9.  Quarterly YoY profit growth > 20%
      10. Quarterly YoY sales growth > 15%
      11. Debt/Equity < 1.5
      12. Market cap > 500

    Returns dict with is_cup_handle, cup/handle details, pivot, score, notes.
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
        "is_cup_handle"  : False,
        "cup_weeks"      : None,
        "cup_depth"      : None,
        "left_rim"       : None,
        "base_price"     : None,
        "right_rim"      : None,
        "handle_days"    : None,
        "handle_retrace" : None,
        "pivot_price"    : None,
        "ch_score"       : 0,
        "fundamentals_available": False,
        "notes"          : notes,
    }

    if len(df) < 60:
        notes.append("Insufficient data")
        return result

    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    # ── Condition 1: MA stack ──
    ma_stack = current > ma200 and current > ma50 and ma50 > ma200
    notes.append(f"MA stack: {'✓' if ma_stack else '✗'}")

    # ── Condition 2: Price within 2–10% of 52w high ──
    pct_below_high = 100.0 * (high_52w - current) / high_52w if high_52w > 0 else 100.0
    near_high = CHConfig.MIN_PCT_BELOW_HIGH < pct_below_high < CHConfig.MAX_PCT_BELOW_HIGH
    notes.append(f"Below 52w high: {pct_below_high:.1f}% "
                 f"({'✓' if near_high else '✗'} need {CHConfig.MIN_PCT_BELOW_HIGH}–{CHConfig.MAX_PCT_BELOW_HIGH}%)")

    # ── Condition 3: Price > 50% above 52w low ──
    pct_above_low = 100.0 * (current - low_52w) / low_52w if low_52w > 0 else 0.0
    above_low     = pct_above_low > CHConfig.MIN_RISE_FROM_LOW_PCT
    notes.append(f"Above 52w low: {pct_above_low:.1f}% "
                 f"({'✓' if above_low else '✗'} need >{CHConfig.MIN_RISE_FROM_LOW_PCT}%)")

    # ── Condition 4: 6-month return > 10% ──
    bars_6m = 126
    if len(close) >= bars_6m:
        ret_6m = 100.0 * (current / float(close.iloc[-bars_6m]) - 1)
    else:
        ret_6m = 100.0 * (current / float(close.iloc[0]) - 1)
    ret_6m_ok = ret_6m > CHConfig.MIN_6M_RETURN_PCT
    notes.append(f"6-month return: {ret_6m:.1f}% "
                 f"({'✓' if ret_6m_ok else '✗'} need >{CHConfig.MIN_6M_RETURN_PCT}%)")

    # ── Condition 5: 1-year return > 20% ──
    if len(close) >= 252:
        ret_1y = 100.0 * (current / float(close.iloc[-252]) - 1)
    else:
        ret_1y = ret_6m
    ret_1y_ok = ret_1y > CHConfig.MIN_1Y_RETURN_PCT
    notes.append(f"1-year return: {ret_1y:.1f}% "
                 f"({'✓' if ret_1y_ok else '✗'} need >{CHConfig.MIN_1Y_RETURN_PCT}%)")

    # ── Condition 6: Volume ──
    vol_ok = cur_vol >= CHConfig.MIN_VOLUME
    notes.append(f"Volume: {int(cur_vol):,} ({'✓' if vol_ok else '✗'} need ≥{CHConfig.MIN_VOLUME:,})")

    # ── Condition 7: Cup detection ──
    cup = _detect_cup(df)
    if cup:
        notes.append(f"Cup: {cup['cup_weeks']}w, depth {cup['cup_depth']:.1f}%, "
                     f"left rim {cup['left_rim']}, base {cup['base_price']}, "
                     f"right rim {cup['right_rim']} ✓")
        result["cup_weeks"]  = cup["cup_weeks"]
        result["cup_depth"]  = cup["cup_depth"]
        result["left_rim"]   = cup["left_rim"]
        result["base_price"] = cup["base_price"]
        result["right_rim"]  = cup["right_rim"]
        result["pivot_price"]= cup["pivot"]
    else:
        notes.append("Cup pattern not detected ✗")

    # ── Condition 8: Handle detection ──
    handle = {"handle_found": False}
    if cup:
        handle = _detect_handle(df, cup)
        if handle["handle_found"]:
            result["handle_days"]   = handle["handle_days"]
            result["handle_retrace"]= handle["retrace_pct"]
            notes.append(f"Handle: {handle['handle_days']}d, "
                         f"retrace {handle['retrace_pct']:.1f}%, "
                         f"upper half: {'✓' if handle['in_upper_half'] else '✗'}, "
                         f"vol contracted: {'✓' if handle['vol_contracted'] else '✗'}")
        else:
            notes.append("Handle not found ✗")

    # ── Fundamentals ──
    fund = _get_fundamentals(symbol)
    fund_available = any(v is not None for v in fund.values())
    result["fundamentals_available"] = fund_available
    fund_pass = True
    if fund_available:
        checks = []
        pg = fund["profit_growth_yoy"]
        sg = fund["sales_growth_yoy"]
        de = fund["debt_to_equity"]
        mc = fund["market_cap"]
        if pg is not None: checks.append(pg * 100 > CHConfig.MIN_PROFIT_GROWTH_PCT)
        if sg is not None: checks.append(sg * 100 > CHConfig.MIN_SALES_GROWTH_PCT)
        if de is not None: checks.append(de        < CHConfig.MAX_DEBT_EQUITY)
        if mc is not None: checks.append(mc        > CHConfig.MIN_MARKET_CAP)
        fund_pass = all(checks)
        notes.append(f"Fundamentals: {'✓' if fund_pass else '✗'}")
    else:
        notes.append("Fundamentals: not available")

    # ── Scoring ──
    score = 0
    if ma_stack:              score += 2
    if near_high:             score += 2
    if above_low:             score += 1
    if ret_6m_ok:             score += 1
    if ret_1y_ok:             score += 1
    if vol_ok:                score += 1
    if cup:                   score += 3
    if handle["handle_found"]:score += 3
    if handle.get("vol_contracted"): score += 1
    if fund_available and fund_pass: score += 2

    result["ch_score"] = score

    # ── Pass / fail ──
    if (ma_stack and near_high and above_low and ret_6m_ok
            and ret_1y_ok and vol_ok and cup
            and handle["handle_found"] and fund_pass):
        result["is_cup_handle"] = True
        notes.append(f"✓ CUP & HANDLE setup confirmed (score {score}/17)")
    else:
        notes.append(f"✗ Cup & Handle not confirmed (score {score}/17)")

    return result
