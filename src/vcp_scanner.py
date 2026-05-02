#!/usr/bin/env python3
"""
Minervini VCP Pattern Scanner — Python Script
Detects: Swing Highs/Lows, VCP contractions, Pivot Point
Works with: yfinance (free) for NSE stocks
Install dependencies:
    pip install yfinance pandas numpy mplfinance matplotlib openpyxl
Usage:
    python vcp_scanner.py
    Modify STOCKS list with NSE symbols (e.g., "RELIANCE.NS")
"""
# ========== FIX 1: Set non-interactive backend BEFORE importing pyplot ==========
import matplotlib
matplotlib.use('Agg')  # Use non-interactive backend (no GUI, avoids threading issues)
# ===============================================================================

import os
import warnings
warnings.filterwarnings('ignore')  # Suppress deprecation warnings

import yfinance as yf
import pandas as pd
import numpy as np
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.lines as mlines
from datetime import datetime, timedelta

# ========== FIX 2: Configure matplotlib to be thread-safe ==========
plt.switch_backend('Agg')  # Ensure Agg backend is used
# ===================================================================

ROOT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
CHART_DIR  = os.path.join(OUTPUT_DIR, "charts")
os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(CHART_DIR,  exist_ok=True)

BENCHMARK_CACHE = {}
BENCHMARK_SYMBOLS = {
    "NSE": "^NSEI",
    "US" : "^GSPC"
}

def get_benchmark_symbol(symbol: str) -> str:
    return BENCHMARK_SYMBOLS["NSE"] if symbol.endswith(".NS") else BENCHMARK_SYMBOLS["US"]

def get_benchmark_name(symbol: str) -> str:
    return "Nifty 50" if symbol.endswith(".NS") else "S&P 500"

def get_benchmark_data(symbol, start, end):
    cache_key = (symbol, start, end)
    if cache_key in BENCHMARK_CACHE:
        return BENCHMARK_CACHE[cache_key]
    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    BENCHMARK_CACHE[cache_key] = df
    return df

def compute_rs(symbol: str, df: pd.DataFrame, benchmark_df: pd.DataFrame) -> float | None:
    if df.empty or benchmark_df.empty:
        return None
    def _extract_close(series_or_df):
        if isinstance(series_or_df, pd.Series):
            return series_or_df
        if isinstance(series_or_df, pd.DataFrame):
            if "Close" in series_or_df.columns:
                close = series_or_df["Close"]
                if isinstance(close, pd.DataFrame):
                    return close.iloc[:, 0]
                return close
            if isinstance(series_or_df.columns, pd.MultiIndex):
                close_cols = [col for col in series_or_df.columns if col[-1] == "Close"]
                if close_cols:
                    return series_or_df[close_cols[0]]
            return None
        return None
    if "Close" not in df.columns and not (isinstance(df.columns, pd.MultiIndex) and any(col[-1] == "Close" for col in df.columns)):
        return None
    if "Close" not in benchmark_df.columns and not (isinstance(benchmark_df.columns, pd.MultiIndex) and any(col[-1] == "Close" for col in benchmark_df.columns)):
        return None
    symbol_close = _extract_close(df)
    benchmark_close = _extract_close(benchmark_df)
    if symbol_close is None or benchmark_close is None:
        return None
    if len(symbol_close) >= 252:
        symbol_start = float(symbol_close.iloc[-252])
    else:
        symbol_start = float(symbol_close.iloc[0])
    if len(benchmark_close) >= 252:
        bench_start = float(benchmark_close.iloc[-252])
    else:
        bench_start = float(benchmark_close.iloc[0])
    if symbol_start <= 0 or bench_start <= 0:
        return None
    symbol_return = float(symbol_close.iloc[-1]) / symbol_start - 1
    benchmark_return = float(benchmark_close.iloc[-1]) / bench_start - 1
    return round(100 * (symbol_return - benchmark_return), 2)

# ─────────────────────────────────────────────
# CONFIG — edit these
# ─────────────────────────────────────────────
def get_nse500_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    df = pd.read_csv(url)
    symbols = df["Symbol"].tolist()
    symbols = [s + ".NS" for s in symbols]
    return symbols

def get_sp500_symbols():
    url = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"
    df = pd.read_csv(url)
    symbols = df["Symbol"].tolist()
    symbols = [s.replace(".", "-") for s in symbols]
    return symbols

# STOCKS = get_nse500_symbols()
STOCKS = get_sp500_symbols()
# STOCKS = [
#     "ATLANTAELE.NS",
#     "ANANDRATHI.NS",
#     "POWERINDIA.NS",
#     "AVANTIFEED.NS",
#     "MTARTECH.NS",
#     "BSE.NS",
#     "KSHINTL.NS",
#     "GODAVARIB.NS"
# ]
SWING_LOOKBACK = 3       # N bars each side to confirm swing high/low
VCP_LOOKBACK_DAYS = 600  # How many days of data to analyse
MIN_CONTRACTIONS = 2     # Minimum number of VCP contractions required
MAX_FINAL_CONTRACTION = 10.0   # Final contraction must be <= 10%
MIN_VOLUME_DRY_UP = 0.9  # Volume on final contraction <= 0.9x of avg
CHART_LOOKBACK_DAYS = 180  # How many days to show on each VCP chart

# ─────────────────────────────────────────────
# SWING HIGH / LOW DETECTION
# Swings are selected using CLOSE only
# ─────────────────────────────────────────────
def find_swing_highs(close: pd.Series, n: int = 5) -> pd.Series:
    """
    Returns a boolean Series. True where close is a swing high:
    close[i] > close[i-n : i] AND close[i] > close[i+1 : i+n+1]
    Uses CLOSING PRICES only.
    """
    highs = pd.Series(False, index=close.index)
    for i in range(n, len(close) - n):
        window_left = close.iloc[i - n:i]
        window_right = close.iloc[i + 1:i + n + 1]
        if close.iloc[i] > window_left.max() and close.iloc[i] > window_right.max():
            highs.iloc[i] = True
    return highs

def find_swing_lows(close: pd.Series, n: int = 5) -> pd.Series:
    """
    Returns a boolean Series. True where close is a swing low.
    Uses CLOSING PRICES only.
    """
    lows = pd.Series(False, index=close.index)
    for i in range(n, len(close) - n):
        window_left = close.iloc[i - n:i]
        window_right = close.iloc[i + 1:i + n + 1]
        if close.iloc[i] < window_left.min() and close.iloc[i] < window_right.min():
            lows.iloc[i] = True
    return lows

# ─────────────────────────────────────────────
# TREND TEMPLATE CHECK (keep as before)
# ─────────────────────────────────────────────
def check_trend_template(df: pd.DataFrame) -> dict:
    """
    Checks all 6 Minervini Trend Template conditions.
    Returns dict with pass/fail for each and overall result.
    """
    close = df["Close"]
    current = close.iloc[-1]
    ma50  = close.rolling(50).mean().iloc[-1]
    ma150 = close.rolling(150).mean().iloc[-1]
    ma200 = close.rolling(200).mean().iloc[-1]
    # 200 MA trend: compare today vs 22 days ago (1 month)
    ma200_1m_ago = close.rolling(200).mean().iloc[-22] if len(close) > 222 else np.nan
    ma200_rising = (ma200 > ma200_1m_ago) if not np.isnan(ma200_1m_ago) else False
    high_52w = close.tail(252).max()
    low_52w  = close.tail(252).min()
    pct_above_low  = 100 * (current - low_52w) / low_52w
    pct_below_high = 100 * (high_52w - current) / high_52w
    conditions = {
        "price_above_ma50"      : current > ma50,
        "price_above_ma150"     : current > ma150,
        "price_above_ma200"     : current > ma200,
        "ma50_gt_ma150"         : ma50 > ma150,
        "ma150_gt_ma200"        : ma150 > ma200,
        "ma200_rising"          : ma200_rising,
        "above_52w_low_30pct"   : pct_above_low > 30,
        "within_52w_high_25pct" : pct_below_high < 25,
    }
    conditions["all_pass"] = all(conditions.values())
    conditions["ma50"]  = round(ma50, 2)
    conditions["ma150"] = round(ma150, 2)
    conditions["ma200"] = round(ma200, 2)
    conditions["pct_above_52w_low"]  = round(pct_above_low, 1)
    conditions["pct_below_52w_high"] = round(pct_below_high, 1)
    return conditions

# ─────────────────────────────────────────────
# HELPER FUNCTIONS FOR VCP
# ─────────────────────────────────────────────
def valid_vcp_pair(prev_c: dict, next_c: dict) -> bool:
    """
    User's exact rule:
    For next contraction to qualify inside previous contraction:
    - close of next top <= high of previous top candle
    - close of next bottom >= low of previous bottom candle
    In notation:
    - close(c2.t) <= high(c1.t)
    - close(c2.b) >= low(c1.b)
    """
    upper_ok = next_c["top_close"] <= prev_c["top_high"]
    lower_ok = next_c["bottom_close"] >= prev_c["bottom_low"]
    return upper_ok and lower_ok

def contraction_tightening(prev_c: dict, next_c: dict) -> bool:
    """Informational check: next contraction % <= previous contraction %."""
    return next_c["contraction_pct"] <= prev_c["contraction_pct"]

def volume_declining(vols: list, allowed_violations: int = 1) -> bool:
    """Volume should generally decline across contractions."""
    violations = sum(1 for i in range(len(vols) - 1) if vols[i] < vols[i + 1])
    return violations <= allowed_violations

def get_recent_pairs_and_triplet(contractions: list):
    """
    Returns:
    - pair_last2: last 2 contractions
    - pair_prev2: previous pair inside last 3 (C1,C2 of the last 3)
    - triplet: last 3 contractions
    """
    pair_last2 = contractions[-2:] if len(contractions) >= 2 else None
    pair_prev2 = contractions[-3:-1] if len(contractions) >= 3 else None
    triplet = contractions[-3:] if len(contractions) >= 3 else None
    return pair_last2, pair_prev2, triplet

# ─────────────────────────────────────────────
# VCP DETECTION
# ─────────────────────────────────────────────
def detect_vcp(df: pd.DataFrame, swing_n: int = 5) -> dict:
    """
    Detects VCP using:
    1. Swing highs/lows selected on CLOSE only
    2. For each contraction:
       - top candle = swing high candle
       - bottom candle = swing low candle
    3. Pair validation uses candle values:
       - close(next top) <= high(previous top candle)
       - close(next bottom) >= low(previous bottom candle)
    4. Grade A:
       - C2 valid inside C1
       - C3 valid inside C2
    5. Grade B:
       - latest 2 valid OR previous 2 valid
    """
    close = df["Close"]
    volume = df["Volume"]
    swing_high_mask = find_swing_highs(close, n=swing_n)
    swing_low_mask  = find_swing_lows(close, n=swing_n)
    swing_highs = close[swing_high_mask]
    swing_lows  = close[swing_low_mask]
    # Build alternating sequence: high → low → high → low
    sh = pd.DataFrame({"price": swing_highs, "type": "H"})
    sl = pd.DataFrame({"price": swing_lows,  "type": "L"})
    swings = pd.concat([sh, sl]).sort_index()
    # Remove consecutive same-type swings (keep the most extreme CLOSE)
    cleaned = []
    for _, row in swings.iterrows():
        if cleaned and cleaned[-1][1] == row["type"]:
            if row["type"] == "H" and row["price"] > cleaned[-1][0]:
                cleaned[-1] = (row["price"], row["type"], row.name)
            elif row["type"] == "L" and row["price"] < cleaned[-1][0]:
                cleaned[-1] = (row["price"], row["type"], row.name)
        else:
            cleaned.append((row["price"], row["type"], row.name))
    # Extract contractions: each High → next Low
    contractions = []
    for i in range(len(cleaned) - 1):
        curr = cleaned[i]
        nxt  = cleaned[i + 1]
        if curr[1] == "H" and nxt[1] == "L":
            top_date = curr[2]
            bot_date = nxt[2]
            # Swing selection is by CLOSE, but store actual candle data too
            top_close = float(df.loc[top_date, "Close"])
            top_high  = float(df.loc[top_date, "High"])
            top_low   = float(df.loc[top_date, "Low"])
            bottom_close = float(df.loc[bot_date, "Close"])
            bottom_high  = float(df.loc[bot_date, "High"])
            bottom_low   = float(df.loc[bot_date, "Low"])
            contraction_pct = 100 * (top_close - bottom_close) / top_close
            vol_slice = volume[top_date:bot_date]
            avg_vol_contraction = vol_slice.mean() if len(vol_slice) > 0 else np.nan
            contractions.append({
                "high_date": top_date,
                "low_date": bot_date,
                # top swing candle (c1.t etc.)
                "top_close": round(top_close, 2),
                "top_high" : round(top_high, 2),
                "top_low"  : round(top_low, 2),
                # bottom swing candle (c1.b etc.)
                "bottom_close": round(bottom_close, 2),
                "bottom_high" : round(bottom_high, 2),
                "bottom_low"  : round(bottom_low, 2),
                # keep old names for display compatibility
                "high_price": round(top_close, 2),
                "low_price" : round(bottom_close, 2),
                "contraction_pct": round(float(contraction_pct), 2),
                "avg_volume": int(avg_vol_contraction) if not np.isnan(avg_vol_contraction) else 0,
            })
    # Keep recent base
    recent_contractions = contractions[-6:] if len(contractions) >= 6 else contractions
    result = {
        "contractions"      : recent_contractions,
        "num_contractions"  : len(recent_contractions),
        "is_vcp"            : False,
        "vcp_quality"       : "none",
        "pivot_price"       : None,
        "final_contraction" : None,
        "volume_dry_up"     : False,
        "notes"             : [],
        "cleaned_swings"    : cleaned,   # stored for chart use
    }
    if len(recent_contractions) < MIN_CONTRACTIONS:
        result["notes"].append(f"Only {len(recent_contractions)} contractions found, need {MIN_CONTRACTIONS}+")
        return result
    pcts = [c["contraction_pct"] for c in recent_contractions]
    vols = [c["avg_volume"] for c in recent_contractions]
    final_pct = pcts[-1]
    tight_final = final_pct <= MAX_FINAL_CONTRACTION
    overall_avg_vol = volume.tail(50).mean()
    final_vol_ratio = vols[-1] / overall_avg_vol if overall_avg_vol > 0 else 1.0
    vol_dry_up = final_vol_ratio <= MIN_VOLUME_DRY_UP
    vol_shrinking = volume_declining(vols, allowed_violations=1)
    within_5pct_high = False
    if "Close" in df.columns:
        high_52w = df["Close"].tail(252).max()
        current_price = df["Close"].iloc[-1]
        pct_below_high = 100 * (high_52w - current_price) / high_52w if high_52w > 0 else 100
        within_5pct_high = pct_below_high <= 5
    pair_last2, pair_prev2, triplet = get_recent_pairs_and_triplet(recent_contractions)
    nested_last2 = False
    nested_prev2 = False
    nested_triplet = False
    # Latest 2
    if pair_last2 is not None:
        nested_last2 = valid_vcp_pair(pair_last2[0], pair_last2[1])
        if nested_last2:
            result["notes"].append("Latest 2 contractions satisfy top/bottom rule")
    # Previous 2 inside last 3
    if pair_prev2 is not None:
        nested_prev2 = valid_vcp_pair(pair_prev2[0], pair_prev2[1])
        if nested_prev2:
            result["notes"].append("Previous 2 contractions satisfy top/bottom rule")
    # Last 3
    if triplet is not None:
        c1, c2, c3 = triplet
        c2_inside_c1 = valid_vcp_pair(c1, c2)
        c3_inside_c2 = valid_vcp_pair(c2, c3)
        c2_tightening = contraction_tightening(c1, c2)
        c3_tightening = contraction_tightening(c2, c3)
        nested_triplet = c2_inside_c1 and c3_inside_c2
        result["notes"].append(
            f"Last 3 contraction %: C1={c1['contraction_pct']:.2f}%, "
            f"C2={c2['contraction_pct']:.2f}%, C3={c3['contraction_pct']:.2f}%"
        )
        result["notes"].append(
            f"C1.t close/high = {c1['top_close']}/{c1['top_high']}, "
            f"C2.t close/high = {c2['top_close']}/{c2['top_high']}, "
            f"C3.t close/high = {c3['top_close']}/{c3['top_high']}"
        )
        result["notes"].append(
            f"C1.b close/low = {c1['bottom_close']}/{c1['bottom_low']}, "
            f"C2.b close/low = {c2['bottom_close']}/{c2['bottom_low']}, "
            f"C3.b close/low = {c3['bottom_close']}/{c3['bottom_low']}"
        )
        if c2_inside_c1:
            result["notes"].append("C2 satisfies: close(C2.t) <= high(C1.t) and close(C2.b) >= low(C1.b)")
        else:
            result["notes"].append("C2 does NOT satisfy top/bottom rule against C1")
        if c3_inside_c2:
            result["notes"].append("C3 satisfies: close(C3.t) <= high(C2.t) and close(C3.b) >= low(C2.b)")
        else:
            result["notes"].append("C3 does NOT satisfy top/bottom rule against C2")
        if c2_tightening and c3_tightening:
            result["notes"].append("Contraction percentages are tightening")
        else:
            result["notes"].append("Contraction percentages are not fully tightening")
    # Pivot = most recent swing high price (close-based swing)
    if cleaned and cleaned[-1][1] == "H":
        pivot = cleaned[-1][0]
    elif len(cleaned) >= 2 and cleaned[-2][1] == "H":
        pivot = cleaned[-2][0]
    else:
        pivot = None
    result["final_contraction"] = round(final_pct, 2)
    result["volume_dry_up"]     = vol_dry_up
    result["pivot_price"]       = round(float(pivot), 2) if pivot is not None else None
    result["vol_ratio_final"]   = round(float(final_vol_ratio), 2)
    score = 0
    if nested_triplet:
        score += 4
        result["notes"].append("3-step structure valid: C3 inside C2 inside C1")
    elif nested_last2 or nested_prev2:
        score += 2
        result["notes"].append("2-step structure valid")
    else:
        result["notes"].append("Nested VCP structure not valid")
    if tight_final:
        score += 2
        result["notes"].append(f"Final contraction tight: {final_pct:.1f}%")
    else:
        result["notes"].append(f"Final contraction too wide: {final_pct:.1f}% (need <={MAX_FINAL_CONTRACTION}%)")
    if vol_dry_up:
        score += 2
        result["notes"].append(f"Volume dry-up confirmed: {final_vol_ratio:.1f}x avg")
    else:
        result["notes"].append(f"Volume NOT dried up: {final_vol_ratio:.1f}x avg (need <={MIN_VOLUME_DRY_UP}x)")
    if vol_shrinking:
        score += 1
        result["notes"].append("Volume generally declining across contractions")
    if len(recent_contractions) >= 3:
        score += 1
        result["notes"].append(f"{len(recent_contractions)} contractions found (ideal: 3–4)")
    else:
        result["notes"].append(f"{len(recent_contractions)} contractions found")
    if pct_below_high <= 5:
        score += 1
        result["notes"].append("Price is within 5% of the 52-week high")
    result["vcp_score"] = score
    # Final grading
    if nested_triplet and tight_final:
        result["is_vcp"] = True
        result["vcp_quality"] = "A (3-step valid VCP)"
    elif nested_last2 and tight_final:
        result["is_vcp"] = True
        result["vcp_quality"] = "B (latest 2 valid VCP)"
    elif nested_prev2 and tight_final:
        result["is_vcp"] = True
        result["vcp_quality"] = "C (previous 2 of last 3 valid VCP)"
    elif nested_triplet or nested_last2 or nested_prev2:
        result["is_vcp"] = True
        result["vcp_quality"] = "D (Structure valid, needs tightening)"
    else:
        result["is_vcp"] = False
        result["vcp_quality"] = "Fail"
    return result

# ─────────────────────────────────────────────
# CHART VISUALISATION ← FIXED: No GUI, no threading issues
# ─────────────────────────────────────────────
_GRADE_COLOR = {"A": "#00c853", "B": "#2979ff", "C": "#ff6d00", "D": "#aa00ff"}
_EMA_STYLE   = {
    "EMA_10" : ("#e65100", 0.9),
    "EMA_20" : ("#0277bd", 0.9),
    "EMA_50" : ("#1b5e20", 1.2),
    "EMA_150": ("#4a148c", 1.2),
    "EMA_200": ("#b71c1c", 1.4),
}
_BAND_COLORS = ["#ffeb3b", "#ff9800", "#f44336", "#ce93d8", "#80cbc4", "#a5d6a7"]

def _grade_from_quality(vcp_quality: str) -> str:
    """Extract single letter grade from the quality string."""
    q = vcp_quality or ""
    if q.startswith("A"): return "A"
    if q.startswith("B"): return "B"
    if q.startswith("C"): return "C"
    if q.startswith("D"): return "D"
    return "Fail"

def plot_vcp_chart(symbol: str, df_full: pd.DataFrame, vcp: dict,
                   trend: dict, rs_value, save_path: str):
    """
    Dark-theme candlestick chart annotated with:
      • EMA 10 / 20 / 50 / 150 / 200
      • Swing high (▼) and swing low (▲) markers
      • Shaded contraction bands C1…Cn with % label
      • Pivot breakout line + label
      • Volume panel with dry-up highlight
      • Grade badge and score
      • Trend template summary footer
    
    FIX: Uses Agg backend (no GUI) and properly closes all figures.
    """
    grade       = _grade_from_quality(vcp.get("vcp_quality", ""))
    grade_color = _GRADE_COLOR.get(grade, "#9e9e9e")
    contractions= vcp.get("contractions", [])
    cleaned     = vcp.get("cleaned_swings", [])
    pivot       = vcp.get("pivot_price")
    vol_dry_up  = vcp.get("volume_dry_up", False)
    vol_ratio   = vcp.get("vol_ratio_final", None)

    # ── trim to chart window ──
    chart_start = df_full.index[-1] - pd.Timedelta(days=CHART_LOOKBACK_DAYS)
    df = df_full[df_full.index >= chart_start].copy()
    if len(df) < 20:
        df = df_full.tail(60).copy()

    currency = "₹" if symbol.endswith(".NS") else "$"
    n = len(df)   # number of bars shown

    # ── EMA addplots ──
    ema_addplots  = []
    ema_legend_handles = []
    for col, (color, lw) in _EMA_STYLE.items():
        if col in df_full.columns:
            series = df_full[col].reindex(df.index)
        else:
            span = int(col.split("_")[1])
            series = df["Close"].ewm(span=span, adjust=False).mean()
        ema_addplots.append(mpf.make_addplot(series, panel=0, color=color,
                                             width=lw, alpha=0.85))
        ema_legend_handles.append(
            mlines.Line2D([], [], color=color, linewidth=lw,
                          label=col.replace("_", " "))
        )

    # ── swing markers ──
    sh_marker = pd.Series(np.nan, index=df.index)
    sl_marker = pd.Series(np.nan, index=df.index)
    for price, stype, date in cleaned:
        if date in df.index:
            if stype == "H":
                sh_marker[date] = df.loc[date, "High"] * 1.006
            else:
                sl_marker[date] = df.loc[date, "Low"]  * 0.994

    marker_plots = []
    if sh_marker.notna().any():
        marker_plots.append(mpf.make_addplot(
            sh_marker, type="scatter", markersize=55,
            marker="v", color="#f44336", panel=0))
    if sl_marker.notna().any():
        marker_plots.append(mpf.make_addplot(
            sl_marker, type="scatter", markersize=55,
            marker="^", color="#4caf50", panel=0))

    # ── volume colours: highlight final contraction window ──
    vol_colors = []
    final_start = (contractions[-1]["high_date"]
                   if contractions else df.index[-20])
    for i, idx in enumerate(df.index):
        up = df["Close"].iloc[i] >= df["Close"].iloc[i - 1] if i > 0 else True
        in_final = (idx >= final_start) and vol_dry_up
        if in_final:
            vol_colors.append("#ef5350" if not up else "#26a69a")
        else:
            vol_colors.append("#26a69a" if up else "#ef5350")

    vol_plot = mpf.make_addplot(df["Volume"], type="bar", panel=1,
                                color=vol_colors, alpha=0.75)

    all_addplots = ema_addplots + marker_plots + [vol_plot]

    # ── mplfinance style ──
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mpf.make_marketcolors(
            up="#26a69a", down="#ef5350",
            edge={"up": "#26a69a", "down": "#ef5350"},
            wick={"up": "#80cbc4", "down": "#ef9a9a"},
            volume="inherit",
        ),
        facecolor="#0d0d0d", figcolor="#0d0d0d",
        gridcolor="#1c1c1c", gridstyle="--",
        rc={
            "axes.labelcolor": "#e0e0e0",
            "xtick.color": "#9e9e9e",
            "ytick.color": "#9e9e9e",
        }
    )

    title = (f"{symbol}   {currency}{float(df['Close'].iloc[-1]):.2f}"
             f"   VCP Grade: {grade}   Score: {vcp.get('vcp_score','?')}/11")

    fig, axes = mpf.plot(
        df, type="candle", style=style,
        addplot=all_addplots,
        volume=False,
        panel_ratios=(3, 1),
        figsize=(16, 9),
        title=title,
        returnfig=True,
        tight_layout=True,
    )

    ax_price = axes[0]
    ax_vol   = axes[2]   # mplfinance inserts spacer at index 1

    # ── contraction bands ──
    for i, c in enumerate(contractions):
        hd, ld = c["high_date"], c["low_date"]
        # clip to chart window
        if ld < df.index[0]:
            continue
        hd_c = hd if hd >= df.index[0] else df.index[0]
        ld_c = ld if ld <= df.index[-1] else df.index[-1]
        try:
            x0 = df.index.get_loc(hd_c) if hd_c in df.index else df.index.searchsorted(hd_c)
            x1 = df.index.get_loc(ld_c) if ld_c in df.index else df.index.searchsorted(ld_c)
        except Exception:
            continue
        if x0 >= x1:
            continue
        color = _BAND_COLORS[i % len(_BAND_COLORS)]
        band_h = c["top_close"] - c["low_price"]
        rect = plt.Rectangle(
            (x0 - 0.4, c["low_price"]), (x1 - x0 + 0.8), band_h,
            linewidth=1.2, edgecolor=color, facecolor=color,
            alpha=0.12, zorder=2
        )
        ax_price.add_patch(rect)
        # % label centred inside band
        mid_x = (x0 + x1) / 2
        mid_y = c["low_price"] + band_h / 2
        ax_price.text(
            mid_x, mid_y,
            f"C{i+1}\n{c['contraction_pct']:.1f}%",
            color=color, fontsize=7.5, ha="center", va="center",
            fontweight="bold", zorder=5,
            bbox=dict(boxstyle="round,pad=0.25", facecolor="#0d0d0d",
                      edgecolor=color, alpha=0.75, linewidth=0.8)
        )

    # ── pivot line ──
    if pivot:
        ax_price.axhline(pivot, color="#ffeb3b", linewidth=1.4,
                         linestyle="--", alpha=0.9, zorder=6)
        ax_price.text(
            n - 1, pivot * 1.003,
            f"  Pivot {currency}{pivot:.2f}  ← buy above",
            color="#ffeb3b", fontsize=8.5, va="bottom",
            fontweight="bold", zorder=7
        )

    # ── grade badge ──
    ax_price.text(
        0.01, 0.985,
        f"  Grade: {grade}   Score: {vcp.get('vcp_score','?')}/11  ",
        transform=ax_price.transAxes,
        color=grade_color, fontsize=12, fontweight="bold",
        va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.4", facecolor="#0d0d0d",
                  edgecolor=grade_color, linewidth=1.5, alpha=0.85)
    )

    # ── RS annotation ──
    rs_txt = (f"RS vs {get_benchmark_name(symbol)}: {rs_value:+.1f}%"
              if rs_value is not None else "RS: N/A")
    ax_price.text(0.01, 0.915, rs_txt,
                  transform=ax_price.transAxes,
                  color="#ce93d8", fontsize=8.5, va="top")

    # ── volume panel annotation ──
    ax_vol.set_facecolor("#0d0d0d")
    ax_vol.set_ylabel("Volume", color="#9e9e9e", fontsize=8)
    if vol_dry_up:
        ax_vol.text(0.01, 0.92, "Vol dry-up confirmed",
                    transform=ax_vol.transAxes,
                    color="#4caf50", fontsize=8, fontweight="bold", va="top")
    else:
        ratio_txt = f"{vol_ratio:.2f}x" if vol_ratio is not None else "N/A"
        ax_vol.text(0.01, 0.92, f"Vol ratio: {ratio_txt} avg (need ≤{MIN_VOLUME_DRY_UP}x)",
                    transform=ax_vol.transAxes,
                    color="#ff7043", fontsize=8, va="top")

    # ── trend template footer ──
    tt_ok = trend.get("all_pass", False)
    if tt_ok:
        tt_txt = (f"Trend Template: PASS  |  "
                  f"MA50={currency}{trend.get('ma50','?')}  "
                  f"MA150={currency}{trend.get('ma150','?')}  "
                  f"MA200={currency}{trend.get('ma200','?')}  |  "
                  f"+{trend.get('pct_above_52w_low','?')}% above 52w low  "
                  f"-{trend.get('pct_below_52w_high','?')}% below 52w high")
    else:
        tt_txt = "Trend Template: FAIL"
    ax_price.text(0.5, 0.008, tt_txt,
                  transform=ax_price.transAxes,
                  color="#a5d6a7" if tt_ok else "#ef9a9a",
                  fontsize=7.5, ha="center", va="bottom", alpha=0.9)

    # ── EMA + swing legend ──
    ema_legend_handles += [
        mlines.Line2D([], [], marker="v", color="w", markerfacecolor="#f44336",
                      markersize=7, linestyle="None", label="Swing high"),
        mlines.Line2D([], [], marker="^", color="w", markerfacecolor="#4caf50",
                      markersize=7, linestyle="None", label="Swing low"),
    ]
    ax_price.legend(handles=ema_legend_handles, loc="upper right",
                    fontsize=7, facecolor="#0d0d0d", edgecolor="#333",
                    labelcolor="#e0e0e0", ncol=4, framealpha=0.85)

    fig.patch.set_facecolor("#0d0d0d")
    
    # ========== FIX 3: Save and close properly (no plt.show()) ==========
    plt.savefig(save_path, dpi=130, bbox_inches="tight",
                facecolor="#0d0d0d", edgecolor="none")
    plt.close(fig)  # Close the figure to free memory
    plt.close('all')  # Extra safety: close all figures
    # ====================================================================
    
    print(f"  Chart → {save_path}")

# ─────────────────────────────────────────────
# MAIN SCANNER
# ─────────────────────────────────────────────
def scan_stock(symbol: str) -> dict:
    """Download data and run all checks for one stock."""
    end   = datetime.today()
    start = end - timedelta(days=VCP_LOOKBACK_DAYS + 60)  # Extra buffer for MAs
    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    except Exception as e:
        return {"symbol": symbol, "error": str(e)}
    if df.empty or len(df) < 60:
        return {"symbol": symbol, "error": "Insufficient data"}
    # Flatten multi-level columns if present
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    if df.empty or len(df) < 60:
        return {"symbol": symbol, "error": "Insufficient data"}
    for period in [10, 20, 50, 150, 200]:
        df[f"EMA_{period}"] = df["Close"].ewm(span=period, adjust=False).mean()
    current_price = round(float(df["Close"].iloc[-1]), 2)
    # Trend template
    trend = check_trend_template(df)
    # VCP
    vcp = detect_vcp(df, swing_n=SWING_LOOKBACK)
    benchmark_symbol = get_benchmark_symbol(symbol)
    benchmark_name = get_benchmark_name(symbol)
    benchmark_df = get_benchmark_data(benchmark_symbol, start, end)
    rs_value = compute_rs(symbol, df, benchmark_df)
    down_from_52w_high = round(trend["pct_below_52w_high"], 1)
    within_5pct_high = trend["pct_below_52w_high"] <= 5
    if within_5pct_high:
        vcp_score_bonus = 1
    else:
        vcp_score_bonus = 0
    if not trend["all_pass"]:
        vcp["is_vcp"] = False
        if vcp["vcp_quality"] != "Fail":
            vcp["vcp_quality"] = "Filtered (trend template failed)"
    # ── generate chart for every confirmed VCP ──
    if vcp["is_vcp"]:
        safe = symbol.replace(".", "_").replace("/", "_")
        grade = _grade_from_quality(vcp["vcp_quality"])
        fname = f"{grade}_{safe}_{vcp.get('vcp_score', 0)}pts.png"
        save_path = os.path.join(CHART_DIR, fname)
        try:
            plot_vcp_chart(symbol, df, vcp, trend, rs_value, save_path)
        except Exception as e:
            print(f"  Chart error for {symbol}: {e}")
    return {
        "symbol"        : symbol,
        "current_price" : current_price,
        "trend_pass"    : trend["all_pass"],
        "ma50"          : trend["ma50"],
        "ma150"         : trend["ma150"],
        "ma200"         : trend["ma200"],
        "pct_above_52w_low"  : trend["pct_above_52w_low"],
        "pct_below_52w_high" : trend["pct_below_52w_high"],
        "ema_10"        : round(float(df["EMA_10"].iloc[-1]), 2),
        "ema_20"        : round(float(df["EMA_20"].iloc[-1]), 2),
        "ema_50"        : round(float(df["EMA_50"].iloc[-1]), 2),
        "ema_150"       : round(float(df["EMA_150"].iloc[-1]), 2),
        "ema_200"       : round(float(df["EMA_200"].iloc[-1]), 2),
        "rs"            : rs_value,
        "rs_index"      : benchmark_name,
        "down_from_52w_high" : down_from_52w_high,
        "within_5pct_high"  : within_5pct_high,
        "is_vcp"        : vcp["is_vcp"],
        "vcp_quality"   : vcp["vcp_quality"],
        "num_contractions": vcp["num_contractions"],
        "final_contraction_pct": vcp["final_contraction"],
        "volume_dry_up" : vcp["volume_dry_up"],
        "pivot_price"   : vcp["pivot_price"],
        "vol_ratio"     : vcp.get("vol_ratio_final"),
        "contractions"  : vcp["contractions"],
        "vcp_notes"     : vcp["notes"],
        "vcp_score"     : vcp.get("vcp_score"),
        "vcp_score_bonus" : vcp_score_bonus,
        "error"         : None,
    }

def print_result(r: dict):
    sep = "─" * 60
    print(f"\n{sep}")
    if r.get("error"):
        print(f"  {r['symbol']}  ERROR: {r['error']}")
        return
    trend_icon = "✓" if r["trend_pass"] else "✗"
    vcp_icon   = "✓" if r["is_vcp"] else "✗"
    print(f"  {r['symbol']}   ₹{r['current_price']}")
    print(f"  Trend Template : [{trend_icon}]  "
          f"MA50={r['ma50']}  MA150={r['ma150']}  MA200={r['ma200']}")
    print(f"  52w: +{r['pct_above_52w_low']}% above low  |  "
          f"-{r['pct_below_52w_high']}% below high")
    print(f"  VCP Pattern    : [{vcp_icon}]  Quality: {r['vcp_quality']}")
    print(f"  Contractions   : {r['num_contractions']}  |  "
          f"Final contraction: {r['final_contraction_pct']}%")
    print(f"  Volume dry-up  : {'YES' if r['volume_dry_up'] else 'NO'}  "
          f"(ratio: {r['vol_ratio']}x avg)")
    print(f"  Pivot price    : ₹{r['pivot_price']}")
    if r["contractions"]:
        print(f"\n  Contraction history:")
        for i, c in enumerate(r["contractions"], 1):
            print(
                f"    C{i}: {c['high_date'].date()} ₹{c['high_price']} → "
                f"{c['low_date'].date()} ₹{c['low_price']}  "
                f"({c['contraction_pct']}% drop)  vol_avg={c['avg_volume']:,}"
            )
    print(f"\n  Notes:")
    for note in r["vcp_notes"]:
        print(f"    · {note}")

def run_scanner():
    print("=" * 60)
    print("  Minervini VCP Scanner")
    print(f"  Swing lookback: {SWING_LOOKBACK} bars")
    print(f"  Scanning {len(STOCKS)} stocks...")
    print(f"  Charts saved to: {CHART_DIR}")
    print("=" * 60)
    results = []
    for symbol in STOCKS:
        print(f"  Scanning {symbol}...", end="\r")
        r = scan_stock(symbol)
        results.append(r)
        print_result(r)
    # Summary
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    passed_trend = [r for r in results if r.get("trend_pass")]
    passed_vcp   = [r for r in results if r.get("is_vcp")]
    valid_setups = [r for r in results if r.get("trend_pass") and r.get("is_vcp")]
    a_quality    = [r for r in valid_setups if "A" in str(r.get("vcp_quality", ""))]
    print(f"  Trend Template passed : {len(passed_trend)}/{len(results)}")
    print(f"  VCP detected          : {len(passed_vcp)}/{len(results)}")
    print(f"  Trend+VCP setups      : {len(valid_setups)}/{len(results)}")
    print(f"  Grade A setups        : {len(a_quality)}/{len(results)}")
    if a_quality:
        print(f"\n  TOP SETUPS (Grade A VCP):")
        for r in a_quality:
            print(f"    {r['symbol']:20s}  ₹{r['current_price']}  "
                  f"Pivot: ₹{r['pivot_price']}  "
                  f"Final contraction: {r['final_contraction_pct']}%")
    if valid_setups:
        print(f"\n  VALID SETUPS (Trend + VCP):")
        for r in valid_setups:
            print(f"    {r['symbol']:20s}  ₹{r['current_price']}  "
                  f"Pivot: ₹{r['pivot_price']}  "
                  f"Quality: {r['vcp_quality']}")
    elif passed_vcp:
        print(f"\n  VCP SETUPS FOUND (trend template failed for some):")
        for r in passed_vcp:
            print(f"    {r['symbol']:20s}  ₹{r['current_price']}  "
                  f"Pivot: ₹{r['pivot_price']}  "
                  f"Quality: {r['vcp_quality']}")
    return results

# ─────────────────────────────────────────────
# OPTIONAL: Export to Excel
# ─────────────────────────────────────────────
def export_to_excel(results: list, filename: str = "vcp_scan_results.xlsx"):
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    valid_results = [r for r in results if r.get("trend_pass") and r.get("is_vcp") and not r.get("error")]
    rows = []
    for r in valid_results:
        rows.append({
            "Symbol"            : r["symbol"],
            "Price"             : r["current_price"],
            "Trend_Pass"        : r["trend_pass"],
            "MA50"              : r["ma50"],
            "MA150"             : r["ma150"],
            "MA200"             : r["ma200"],
            "EMA_10"            : r.get("ema_10"),
            "EMA_20"            : r.get("ema_20"),
            "EMA_50"            : r.get("ema_50"),
            "EMA_150"           : r.get("ema_150"),
            "EMA_200"           : r.get("ema_200"),
            "RS"                : r.get("rs"),
            "RS_Index"          : r.get("rs_index"),
            "Pct_Above_52w_Low" : r["pct_above_52w_low"],
            "Pct_Below_52w_High": r["pct_below_52w_high"],
            "Down_From_52w_High": r.get("down_from_52w_high"),
            "Within_5pct_High"  : r.get("within_5pct_high"),
            "Is_VCP"            : r["is_vcp"],
            "VCP_Quality"       : r["vcp_quality"],
            "Num_Contractions"  : r["num_contractions"],
            "Final_Contraction" : r["final_contraction_pct"],
            "Volume_Dry_Up"     : r["volume_dry_up"],
            "Vol_Ratio"         : r["vol_ratio"],
            "Pivot_Price"       : r["pivot_price"],
            "VCP_Score"         : r.get("vcp_score"),
            "VCP_Bonus"         : r.get("vcp_score_bonus"),
        })
    df = pd.DataFrame(rows)
    output_path = os.path.join(OUTPUT_DIR, filename)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="VCP_Setups")
    print(f"\n  Results saved to {output_path} ({len(valid_results)} valid Trend+VCP rows)")
    return df

# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    results = run_scanner()
    export_to_excel(results)