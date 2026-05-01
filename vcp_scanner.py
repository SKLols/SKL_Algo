"""
Minervini VCP Pattern Scanner — Python Script
Detects: Swing Highs/Lows, VCP contractions, Pivot Point
Works with: yfinance (free) for NSE stocks

Install dependencies:
    pip install yfinance pandas numpy

Usage:
    python vcp_scanner.py
    Modify STOCKS list with NSE symbols (e.g., "RELIANCE.NS")
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta


# ─────────────────────────────────────────────
# CONFIG — edit these
# ─────────────────────────────────────────────

def get_nse500_symbols():
    url = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"
    df = pd.read_csv(url)
    symbols = df["Symbol"].tolist()
    
    # convert to yfinance format
    symbols = [s + ".NS" for s in symbols]
    return symbols

# def get_sp500_symbols():
#     url = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
#     df = pd.read_html(url)[0]
#     symbols = df["Symbol"].tolist()

#     # Fix tickers like BRK.B → BRK-B (Yahoo format)
#     symbols = [s.replace(".", "-") for s in symbols]

#     return symbols

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

    # Final grading
    if nested_triplet and tight_final:
        result["is_vcp"] = True
        result["vcp_quality"] = "A (3-step valid VCP)"
    elif (nested_last2 or nested_prev2) and tight_final:
        result["is_vcp"] = True
        result["vcp_quality"] = "B (2-step valid VCP)"
    elif nested_triplet or nested_last2 or nested_prev2:
        result["is_vcp"] = True
        result["vcp_quality"] = "C (Structure valid, needs tightening)"
    else:
        result["is_vcp"] = False
        result["vcp_quality"] = "Fail"

    return result


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

    # 🔥 ADD THIS
    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]

    current_price = round(float(df["Close"].iloc[-1]), 2)

    # Trend template
    trend = check_trend_template(df)

    # VCP
    vcp = detect_vcp(df, swing_n=SWING_LOOKBACK)

    # Show/allow VCP only when trend template passes
    if not trend["all_pass"]:
        vcp["is_vcp"] = False
        if vcp["vcp_quality"] != "Fail":
            vcp["vcp_quality"] = "Filtered (trend template failed)"

    return {
        "symbol"        : symbol,
        "current_price" : current_price,
        "trend_pass"    : trend["all_pass"],
        "ma50"          : trend["ma50"],
        "ma150"         : trend["ma150"],
        "ma200"         : trend["ma200"],
        "pct_above_52w_low"  : trend["pct_above_52w_low"],
        "pct_below_52w_high" : trend["pct_below_52w_high"],
        "is_vcp"        : vcp["is_vcp"],
        "vcp_quality"   : vcp["vcp_quality"],
        "num_contractions": vcp["num_contractions"],
        "final_contraction_pct": vcp["final_contraction"],
        "volume_dry_up" : vcp["volume_dry_up"],
        "pivot_price"   : vcp["pivot_price"],
        "vol_ratio"     : vcp.get("vol_ratio_final"),
        "contractions"  : vcp["contractions"],
        "vcp_notes"     : vcp["notes"],
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
    a_quality    = [r for r in results if "A" in str(r.get("vcp_quality", ""))]

    print(f"  Trend Template passed : {len(passed_trend)}/{len(results)}")
    print(f"  VCP detected          : {len(passed_vcp)}/{len(results)}")
    print(f"  Grade A setups        : {len(a_quality)}/{len(results)}")

    if a_quality:
        print(f"\n  TOP SETUPS (Grade A VCP):")
        for r in a_quality:
            print(f"    {r['symbol']:20s}  ₹{r['current_price']}  "
                  f"Pivot: ₹{r['pivot_price']}  "
                  f"Final contraction: {r['final_contraction_pct']}%")

    if passed_vcp and not a_quality:
        print(f"\n  VCP SETUPS FOUND:")
        for r in passed_vcp:
            print(f"    {r['symbol']:20s}  ₹{r['current_price']}  "
                  f"Pivot: ₹{r['pivot_price']}  "
                  f"Quality: {r['vcp_quality']}")

    return results


# ─────────────────────────────────────────────
# OPTIONAL: Export to CSV
# ─────────────────────────────────────────────
def export_to_csv(results: list, filename: str = "vcp_scan_results.csv"):
    rows = []
    for r in results:
        if r.get("error"):
            continue
        rows.append({
            "Symbol"            : r["symbol"],
            "Price"             : r["current_price"],
            "Trend_Pass"        : r["trend_pass"],
            "MA50"              : r["ma50"],
            "MA150"             : r["ma150"],
            "MA200"             : r["ma200"],
            "Pct_Above_52w_Low" : r["pct_above_52w_low"],
            "Pct_Below_52w_High": r["pct_below_52w_high"],
            "Is_VCP"            : r["is_vcp"],
            "VCP_Quality"       : r["vcp_quality"],
            "Num_Contractions"  : r["num_contractions"],
            "Final_Contraction" : r["final_contraction_pct"],
            "Volume_Dry_Up"     : r["volume_dry_up"],
            "Vol_Ratio"         : r["vol_ratio"],
            "Pivot_Price"       : r["pivot_price"],
        })
    df = pd.DataFrame(rows)
    df.to_csv(filename, index=False)
    print(f"\n  Results saved to {filename}")
    return df


# ─────────────────────────────────────────────
# RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    results = run_scanner()
    export_to_csv(results)