"""
setups/darvas.py — Darvas Box Breakout detection.

Nicolas Darvas's method: price forms a "box" (consolidation zone between
a ceiling and a floor), then breaks out on expanding volume.

Your logic incorporated:
  - Price within 10% of 52-week high (near-high consolidation)
  - Price > 100% above 52-week low (strong prior uptrend)
  - Price between 10 and 1000
  - Volume > 100,000

Additional Darvas logic added:
  - Box detection: 3+ weeks of price contained between box_top and box_bottom
  - Box ceiling tolerance: highs can exceed previous box top by ≤ 1.5%
  - Volume declining inside the box (compression), then surge on breakout
  - Box tightness: box range ≤ 15% of box top price

Public API:
    detect_darvas(df) -> dict
"""
import numpy as np
import pandas as pd

from config import Darvas as DarvasConfig


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _find_box(df: pd.DataFrame, lookback_weeks: int) -> dict | None:
    """
    Scan the most recent `lookback_weeks` of data for a Darvas box.

    A box is formed when:
      1. A new 52-week high is made (box ceiling established).
      2. Price then stays within BOX_TOLERANCE_PCT of that ceiling for
         at least MIN_BOX_WEEKS without making a new high.
      3. A floor (box bottom) is defined as the lowest close during
         that consolidation period.

    Returns a dict with box_top, box_bottom, box_range_pct, box_weeks,
    or None if no valid box is found.
    """
    lookback_bars = lookback_weeks * 5   # approximate trading days
    df_look = df.tail(lookback_bars).copy()

    high_52w = float(df["High"].tail(252).max())
    tol      = DarvasConfig.BOX_TOLERANCE_PCT / 100.0

    # Walk backwards to find where the current consolidation started
    box_top    = float(df_look["High"].iloc[-1])
    box_start  = len(df_look) - 1

    for i in range(len(df_look) - 2, -1, -1):
        bar_high = float(df_look["High"].iloc[i])
        # If this bar's high exceeds box_top by more than tolerance → box started after this bar
        if bar_high > box_top * (1 + tol):
            box_start = i + 1
            break
        box_top = max(box_top, bar_high)

    box_df     = df_look.iloc[box_start:]
    box_weeks  = len(box_df) / 5.0
    box_bottom = float(box_df["Low"].min())

    if box_top <= 0 or box_bottom <= 0:
        return None

    box_range_pct = 100.0 * (box_top - box_bottom) / box_top

    return {
        "box_top"       : round(box_top,       2),
        "box_bottom"    : round(box_bottom,    2),
        "box_range_pct" : round(box_range_pct, 2),
        "box_weeks"     : round(box_weeks,     1),
        "high_52w"      : round(high_52w,      2),
    }


# ─────────────────────────────────────────────
# MAIN DETECTION
# ─────────────────────────────────────────────

def detect_darvas(df: pd.DataFrame) -> dict:
    """
    Detect a Darvas Box breakout setup.

    Conditions checked:
      FROM YOUR LOGIC:
        1. Price within 0–10% of 52-week high
        2. Price > 100% above 52-week low (strong prior move)
        3. Price between $10 and $1000
        4. Volume > 100,000

      ADDITIONAL DARVAS CONDITIONS:
        5. A valid box exists (3+ weeks of tight consolidation near highs)
        6. Box range ≤ 15% (tight consolidation)
        7. Volume declining inside the box (compression before breakout)
        8. Current price near or above box top (setup ready / breaking out)

    Returns dict with is_darvas, box details, score, and notes.
    """
    close   = df["Close"]
    high    = df["High"]
    low     = df["Low"]
    volume  = df["Volume"]

    current  = float(close.iloc[-1])
    cur_vol  = float(volume.iloc[-1])
    high_52w = float(high.tail(252).max())
    low_52w  = float(low.tail(252).min())

    notes = []

    result = {
        "is_darvas"      : False,
        "box_top"        : None,
        "box_bottom"     : None,
        "box_range_pct"  : None,
        "box_weeks"      : None,
        "darvas_score"   : 0,
        "notes"          : notes,
    }

    # ── Guard: minimum data ──
    if len(df) < 60:
        notes.append("Insufficient data")
        return result

    # ── Condition 1: Price within 0–10% of 52w high ──
    pct_below_high = 100.0 * (high_52w - current) / high_52w if high_52w > 0 else 100.0
    near_high      = 0.0 < pct_below_high < DarvasConfig.MAX_PCT_BELOW_HIGH
    notes.append(f"Price {pct_below_high:.1f}% below 52w high "
                 f"({'✓' if near_high else '✗'} need 0–{DarvasConfig.MAX_PCT_BELOW_HIGH}%)")

    # ── Condition 2: Price > 100% above 52w low ──
    pct_above_low  = 100.0 * (current - low_52w) / low_52w if low_52w > 0 else 0.0
    strong_uptrend = pct_above_low > DarvasConfig.MIN_RISE_FROM_LOW_PCT
    notes.append(f"Price {pct_above_low:.1f}% above 52w low "
                 f"({'✓' if strong_uptrend else '✗'} need >{DarvasConfig.MIN_RISE_FROM_LOW_PCT}%)")

    # ── Condition 3: Price range filter ──
    price_ok = DarvasConfig.MIN_PRICE <= current <= DarvasConfig.MAX_PRICE
    notes.append(f"Price {current:.2f} "
                 f"({'✓' if price_ok else '✗'} need {DarvasConfig.MIN_PRICE}–{DarvasConfig.MAX_PRICE})")

    # ── Condition 4: Volume filter ──
    vol_ok = cur_vol >= DarvasConfig.MIN_VOLUME
    notes.append(f"Volume {int(cur_vol):,} "
                 f"({'✓' if vol_ok else '✗'} need ≥{DarvasConfig.MIN_VOLUME:,})")

    # Early exit if basic conditions fail
    if not (near_high and strong_uptrend and price_ok and vol_ok):
        notes.append("Basic conditions not met — skipping box detection")
        return result

    # ── Condition 5 & 6: Box detection ──
    box = _find_box(df, DarvasConfig.BOX_LOOKBACK_WEEKS)
    if box is None:
        notes.append("No Darvas box found")
        return result

    result["box_top"]       = box["box_top"]
    result["box_bottom"]    = box["box_bottom"]
    result["box_range_pct"] = box["box_range_pct"]
    result["box_weeks"]     = box["box_weeks"]

    box_valid   = box["box_weeks"] >= DarvasConfig.MIN_BOX_WEEKS
    box_tight   = box["box_range_pct"] <= DarvasConfig.MAX_BOX_RANGE_PCT
    notes.append(f"Box: {box['box_weeks']:.1f} weeks, range {box['box_range_pct']:.1f}% "
                 f"({'✓' if box_valid and box_tight else '✗'})")

    # ── Condition 7: Volume declining inside box (compression) ──
    box_bars        = int(box["box_weeks"] * 5)
    box_vol         = volume.tail(box_bars)
    avg_vol_50      = float(volume.tail(50).mean())
    avg_vol_box     = float(box_vol.mean()) if len(box_vol) > 0 else avg_vol_50
    vol_compressed  = avg_vol_box < avg_vol_50 * (1 - DarvasConfig.MIN_VOLUME_DECLINE_PCT / 100.0)
    notes.append(f"Volume inside box: {avg_vol_box:,.0f} vs 50-day avg {avg_vol_50:,.0f} "
                 f"({'✓ compressed' if vol_compressed else '✗ not compressed'})")

    # ── Condition 8: Price near or at box top (ready to break) ──
    near_box_top = current >= box["box_top"] * (1 - 0.03)   # within 3% of box top
    notes.append(f"Price vs box top {box['box_top']}: "
                 f"{'✓ near breakout' if near_box_top else '✗ not near box top'}")

    # ── Scoring ──
    score = 0
    if near_high:       score += 2
    if strong_uptrend:  score += 1
    if box_valid:       score += 2
    if box_tight:       score += 2
    if vol_compressed:  score += 2
    if near_box_top:    score += 2
    if vol_ok:          score += 1

    result["darvas_score"] = score

    # ── Pass/fail: must meet all core conditions ──
    if near_high and strong_uptrend and price_ok and vol_ok and box_valid and box_tight:
        result["is_darvas"] = True
        notes.append(f"✓ DARVAS BOX setup confirmed (score {score}/12)")
    else:
        notes.append(f"✗ Darvas Box not confirmed (score {score}/12)")

    return result
