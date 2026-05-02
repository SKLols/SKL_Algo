#!/usr/bin/env python3
"""
scanner.py — Main entry point for the Minervini stock scanner.

Orchestrates:
  1. Load stock universe (data/universe.py)
  2. Download OHLCV + compute EMAs (data/fetcher.py)
  3. Run Trend Template filter (indicators/trend_template.py)
  4. Run VCP detection (setups/vcp.py)
  5. Generate charts for confirmed setups (output/charts.py)
  6. Print results + summary (output/console.py)
  7. Export to Excel (output/exporter.py)

To add a new setup (Darvas, Breakout etc.):
  - Import detect_X from setups/X.py
  - Call it inside scan_stock() after the trend template check
  - Add its result keys to the returned dict
  - Add a summary section in run_scanner()
"""
import os
import sys

# ── Make sure 'scanner/' is on the path when run directly ──
sys.path.insert(0, os.path.dirname(__file__))

from config import CHART_DIR, Indicators
from data.universe import get_symbols
from data.fetcher import fetch_stock, get_benchmark_symbol, get_benchmark_name, get_benchmark_data, compute_rs
from indicators.trend_template import check_trend_template
from setups.vcp import detect_vcp
from output.charts import plot_vcp_chart, _grade_from_quality
from output.console import print_result, print_summary
from output.exporter import export_vcp_to_excel

os.makedirs(CHART_DIR, exist_ok=True)


# ─────────────────────────────────────────────
# SINGLE STOCK SCAN
# ─────────────────────────────────────────────

def scan_stock(symbol: str) -> dict:
    """
    Download data and run all checks for one stock.

    Returns a flat result dict with all fields needed by console, chart,
    and Excel export. Returns {"symbol": symbol, "error": "..."} on failure.
    """
    fetched = fetch_stock(symbol)
    if fetched["error"]:
        return {"symbol": symbol, "error": fetched["error"]}

    df    = fetched["df"]
    start = fetched["start"]
    end   = fetched["end"]

    current_price = round(float(df["Close"].iloc[-1]), 2)

    # ── Stage 1: Trend Template ──
    trend = check_trend_template(df)

    # ── Stage 2: VCP detection ──
    vcp = detect_vcp(df, swing_n=Indicators.SWING_LOOKBACK)

    # ── RS vs benchmark ──
    bm_sym  = get_benchmark_symbol(symbol)
    bm_name = get_benchmark_name(symbol)
    bm_df   = get_benchmark_data(bm_sym, start, end)
    rs_value= compute_rs(symbol, df, bm_df)

    # ── Derived convenience flags ──
    down_from_52w_high = round(trend["pct_below_52w_high"], 1)
    within_5pct_high   = trend["pct_below_52w_high"] <= 5
    vcp_score_bonus    = 1 if within_5pct_high else 0

    # ── Gate VCP on trend template ──
    if not trend["all_pass"]:
        vcp["is_vcp"] = False
        if vcp["vcp_quality"] not in ("none", "Fail"):
            vcp["vcp_quality"] = "Filtered (trend template failed)"

    # ── Generate chart for every confirmed VCP ──
    if vcp["is_vcp"]:
        safe  = symbol.replace(".", "_").replace("/", "_")
        grade = _grade_from_quality(vcp["vcp_quality"])
        fname = f"{grade}_{safe}_{vcp.get('vcp_score', 0)}pts.png"
        fpath = os.path.join(CHART_DIR, fname)
        try:
            plot_vcp_chart(symbol, df, vcp, trend, rs_value, fpath)
            print(f"  Chart → {fpath}")
        except Exception as e:
            print(f"  Chart error for {symbol}: {e}")

    return {
        "symbol"               : symbol,
        "current_price"        : current_price,
        "trend_pass"           : trend["all_pass"],
        "ma50"                 : trend["ma50"],
        "ma150"                : trend["ma150"],
        "ma200"                : trend["ma200"],
        "pct_above_52w_low"    : trend["pct_above_52w_low"],
        "pct_below_52w_high"   : trend["pct_below_52w_high"],
        "ema_10"               : round(float(df["EMA_10"].iloc[-1]),  2),
        "ema_20"               : round(float(df["EMA_20"].iloc[-1]),  2),
        "ema_50"               : round(float(df["EMA_50"].iloc[-1]),  2),
        "ema_150"              : round(float(df["EMA_150"].iloc[-1]), 2),
        "ema_200"              : round(float(df["EMA_200"].iloc[-1]), 2),
        "rs"                   : rs_value,
        "rs_index"             : bm_name,
        "down_from_52w_high"   : down_from_52w_high,
        "within_5pct_high"     : within_5pct_high,
        "is_vcp"               : vcp["is_vcp"],
        "vcp_quality"          : vcp["vcp_quality"],
        "num_contractions"     : vcp["num_contractions"],
        "final_contraction_pct": vcp["final_contraction"],
        "volume_dry_up"        : vcp["volume_dry_up"],
        "pivot_price"          : vcp["pivot_price"],
        "vol_ratio"            : vcp.get("vol_ratio_final"),
        "contractions"         : vcp["contractions"],
        "vcp_notes"            : vcp["notes"],
        "vcp_score"            : vcp.get("vcp_score"),
        "vcp_score_bonus"      : vcp_score_bonus,
        "error"                : None,
    }


# ─────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────

def run_scanner():
    stocks = get_symbols()

    print("=" * 60)
    print("  Minervini VCP Scanner")
    print(f"  Swing lookback : {Indicators.SWING_LOOKBACK} bars")
    print(f"  Scanning       : {len(stocks)} stocks")
    print(f"  Charts saved to: {CHART_DIR}")
    print("=" * 60)

    results = []
    for symbol in stocks:
        print(f"  Scanning {symbol}...", end="\r")
        r = scan_stock(symbol)
        results.append(r)
        print_result(r)

    print_summary(results)
    export_vcp_to_excel(results)
    return results


if __name__ == "__main__":
    run_scanner()
