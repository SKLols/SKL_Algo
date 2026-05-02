"""
setups/vcp.py — Volatility Contraction Pattern detection.

Logic is identical to the original monolithic script.
Imports swing helpers from indicators/swings.py and constants from config.py.

Public API:
    detect_vcp(df) -> dict
"""
import numpy as np
import pandas as pd

from config import VCP as VCPConfig, Indicators
from indicators.swings import build_alternating_swings


# ─────────────────────────────────────────────
# PAIR / TRIPLET VALIDATION HELPERS
# ─────────────────────────────────────────────

def valid_vcp_pair(prev_c: dict, next_c: dict) -> bool:
    """
    True when next_c fits inside prev_c using candle-level values:
      - close(next top)    <= high(prev top candle)    — upper bound
      - close(next bottom) >= low(prev bottom candle)  — lower bound
    """
    return (next_c["top_close"]    <= prev_c["top_high"] and
            next_c["bottom_close"] >= prev_c["bottom_low"])


def contraction_tightening(prev_c: dict, next_c: dict) -> bool:
    """True when next contraction % is smaller than previous — informational only."""
    return next_c["contraction_pct"] <= prev_c["contraction_pct"]


def volume_declining(vols: list[int], allowed_violations: int | None = None) -> bool:
    """
    True when volume generally declines across contractions.
    One violation (a single step where vol rises) is allowed by default.
    """
    if allowed_violations is None:
        allowed_violations = VCPConfig.VOLUME_VIOLATION_ALLOW
    violations = sum(1 for i in range(len(vols) - 1) if vols[i] < vols[i + 1])
    return violations <= allowed_violations


def _get_recent_pairs_and_triplet(contractions: list):
    pair_last2 = contractions[-2:]   if len(contractions) >= 2 else None
    pair_prev2 = contractions[-3:-1] if len(contractions) >= 3 else None
    triplet    = contractions[-3:]   if len(contractions) >= 3 else None
    return pair_last2, pair_prev2, triplet


# ─────────────────────────────────────────────
# VCP DETECTION
# ─────────────────────────────────────────────

def detect_vcp(df: pd.DataFrame, swing_n: int | None = None) -> dict:
    """
    Detect the Volatility Contraction Pattern in a stock DataFrame.

    Algorithm:
      1. Detect swing H/L on CLOSE only (via indicators/swings.py).
      2. Build alternating H→L→H→L sequence, deduplicate same-type runs.
      3. Each H→L pair = one contraction; store close/high/low for each candle.
      4. Validate nesting using candle-level rule (close inside prev high/low).
      5. Grade A: C3 inside C2 inside C1.  Grade B/C: any valid pair.
      6. Score 0–11 across structure, tightness, volume, count, proximity.

    Returns a dict with:
      is_vcp, vcp_quality, vcp_score, pivot_price, final_contraction,
      volume_dry_up, vol_ratio_final, contractions, cleaned_swings, notes.
    """
    if swing_n is None:
        swing_n = Indicators.SWING_LOOKBACK

    close  = df["Close"]
    volume = df["Volume"]

    cleaned = build_alternating_swings(close, n=swing_n)

    # ── Build contraction list (H → L pairs) ──
    contractions = []
    for i in range(len(cleaned) - 1):
        curr, nxt = cleaned[i], cleaned[i + 1]
        if curr[1] != "H" or nxt[1] != "L":
            continue
        top_date, bot_date = curr[2], nxt[2]
        try:
            top_close  = float(df.loc[top_date, "Close"])
            top_high   = float(df.loc[top_date, "High"])
            top_low    = float(df.loc[top_date, "Low"])
            bot_close  = float(df.loc[bot_date, "Close"])
            bot_high   = float(df.loc[bot_date, "High"])
            bot_low    = float(df.loc[bot_date, "Low"])
        except Exception:
            continue

        cpct     = 100.0 * (top_close - bot_close) / top_close
        vol_slice= volume[top_date:bot_date]
        avg_vol  = vol_slice.mean() if len(vol_slice) > 0 else float("nan")

        contractions.append({
            "high_date"      : top_date,
            "low_date"       : bot_date,
            "top_close"      : round(top_close, 2),
            "top_high"       : round(top_high,  2),
            "top_low"        : round(top_low,   2),
            "bottom_close"   : round(bot_close, 2),
            "bottom_high"    : round(bot_high,  2),
            "bottom_low"     : round(bot_low,   2),
            # legacy aliases kept for chart / export compatibility
            "high_price"     : round(top_close, 2),
            "low_price"      : round(bot_close, 2),
            "contraction_pct": round(float(cpct), 2),
            "avg_volume"     : int(avg_vol) if not np.isnan(avg_vol) else 0,
        })

    # Keep only the most recent N contractions
    max_keep = VCPConfig.MAX_CONTRACTIONS_KEPT
    recent   = contractions[-max_keep:] if len(contractions) >= max_keep else contractions

    # ── Default result ──
    result = {
        "contractions"   : recent,
        "num_contractions": len(recent),
        "is_vcp"         : False,
        "vcp_quality"    : "none",
        "pivot_price"    : None,
        "final_contraction": None,
        "volume_dry_up"  : False,
        "vol_ratio_final": None,
        "cleaned_swings" : cleaned,
        "notes"          : [],
    }

    if len(recent) < VCPConfig.MIN_CONTRACTIONS:
        result["notes"].append(
            f"Only {len(recent)} contractions found, need {VCPConfig.MIN_CONTRACTIONS}+")
        return result

    pcts       = [c["contraction_pct"] for c in recent]
    vols       = [c["avg_volume"]       for c in recent]
    final_pct  = pcts[-1]
    tight_final= final_pct <= VCPConfig.MAX_FINAL_CONTRACTION

    overall_avg_vol  = float(volume.tail(50).mean())
    final_vol_ratio  = vols[-1] / overall_avg_vol if overall_avg_vol > 0 else 1.0
    vol_dry_up       = final_vol_ratio <= VCPConfig.MIN_VOLUME_DRY_UP
    vol_shrinking    = volume_declining(vols)

    high_52w      = float(df["Close"].tail(252).max())
    current_price = float(df["Close"].iloc[-1])
    pct_below_high= 100.0 * (high_52w - current_price) / high_52w if high_52w > 0 else 100.0
    within_5pct   = pct_below_high <= VCPConfig.NEAR_HIGH_PCT

    pair_last2, pair_prev2, triplet = _get_recent_pairs_and_triplet(recent)
    nested_last2  = False
    nested_prev2  = False
    nested_triplet= False

    # Validate pairs / triplet
    if pair_last2:
        nested_last2 = valid_vcp_pair(pair_last2[0], pair_last2[1])
        if nested_last2:
            result["notes"].append("Latest 2 contractions satisfy top/bottom rule")

    if pair_prev2:
        nested_prev2 = valid_vcp_pair(pair_prev2[0], pair_prev2[1])
        if nested_prev2:
            result["notes"].append("Previous 2 contractions satisfy top/bottom rule")

    if triplet:
        c1, c2, c3    = triplet
        c2_in_c1      = valid_vcp_pair(c1, c2)
        c3_in_c2      = valid_vcp_pair(c2, c3)
        c2_tight      = contraction_tightening(c1, c2)
        c3_tight      = contraction_tightening(c2, c3)
        nested_triplet= c2_in_c1 and c3_in_c2

        result["notes"].append(
            f"Last 3 contraction %: C1={c1['contraction_pct']:.2f}%, "
            f"C2={c2['contraction_pct']:.2f}%, C3={c3['contraction_pct']:.2f}%")
        result["notes"].append(
            f"C1.t close/high = {c1['top_close']}/{c1['top_high']}, "
            f"C2.t close/high = {c2['top_close']}/{c2['top_high']}, "
            f"C3.t close/high = {c3['top_close']}/{c3['top_high']}")
        result["notes"].append(
            f"C1.b close/low = {c1['bottom_close']}/{c1['bottom_low']}, "
            f"C2.b close/low = {c2['bottom_close']}/{c2['bottom_low']}, "
            f"C3.b close/low = {c3['bottom_close']}/{c3['bottom_low']}")

        result["notes"].append(
            "C2 satisfies: close(C2.t) <= high(C1.t) and close(C2.b) >= low(C1.b)"
            if c2_in_c1 else "C2 does NOT satisfy top/bottom rule against C1")
        result["notes"].append(
            "C3 satisfies: close(C3.t) <= high(C2.t) and close(C3.b) >= low(C2.b)"
            if c3_in_c2 else "C3 does NOT satisfy top/bottom rule against C2")
        result["notes"].append(
            "Contraction percentages are tightening"
            if c2_tight and c3_tight else "Contraction percentages are not fully tightening")

    # ── Pivot = most recent swing high (close-based) ──
    pivot = None
    for price, stype, _ in reversed(cleaned):
        if stype == "H":
            pivot = price
            break

    result["final_contraction"] = round(final_pct, 2)
    result["volume_dry_up"]     = vol_dry_up
    result["vol_ratio_final"]   = round(float(final_vol_ratio), 2)
    result["pivot_price"]       = round(float(pivot), 2) if pivot is not None else None

    # ── Scoring ──
    score = 0
    if nested_triplet:
        score += VCPConfig.SCORE_TRIPLET_NESTED
        result["notes"].append("3-step structure valid: C3 inside C2 inside C1")
    elif nested_last2 or nested_prev2:
        score += VCPConfig.SCORE_PAIR_NESTED
        result["notes"].append("2-step structure valid")
    else:
        result["notes"].append("Nested VCP structure not valid")

    if tight_final:
        score += VCPConfig.SCORE_TIGHT_FINAL
        result["notes"].append(f"Final contraction tight: {final_pct:.1f}%")
    else:
        result["notes"].append(
            f"Final contraction too wide: {final_pct:.1f}% "
            f"(need <={VCPConfig.MAX_FINAL_CONTRACTION}%)")

    if vol_dry_up:
        score += VCPConfig.SCORE_VOL_DRYUP
        result["notes"].append(f"Volume dry-up confirmed: {final_vol_ratio:.1f}x avg")
    else:
        result["notes"].append(
            f"Volume NOT dried up: {final_vol_ratio:.1f}x avg "
            f"(need <={VCPConfig.MIN_VOLUME_DRY_UP}x)")

    if vol_shrinking:
        score += VCPConfig.SCORE_VOL_DECLINING
        result["notes"].append("Volume generally declining across contractions")

    if len(recent) >= 3:
        score += VCPConfig.SCORE_3_CONTRACTIONS
        result["notes"].append(f"{len(recent)} contractions found (ideal: 3–4)")
    else:
        result["notes"].append(f"{len(recent)} contractions found")

    if within_5pct:
        score += VCPConfig.SCORE_NEAR_HIGH
        result["notes"].append(
            f"Price is within {VCPConfig.NEAR_HIGH_PCT}% of the 52-week high")

    result["vcp_score"] = score

    # ── Grading ──
    if nested_triplet and tight_final:
        result["is_vcp"]     = True
        result["vcp_quality"]= "A (3-step valid VCP)"
    elif nested_last2 and tight_final:
        result["is_vcp"]     = True
        result["vcp_quality"]= "B (latest 2 valid VCP)"
    elif nested_prev2 and tight_final:
        result["is_vcp"]     = True
        result["vcp_quality"]= "C (previous 2 of last 3 valid VCP)"
    elif nested_triplet or nested_last2 or nested_prev2:
        result["is_vcp"]     = True
        result["vcp_quality"]= "D (Structure valid, needs tightening)"
    else:
        result["is_vcp"]     = False
        result["vcp_quality"]= "Fail"

    return result
