#!/usr/bin/env python3
"""
scanner.py — Main entry point for the Minervini stock scanner.

Runs all setups for every stock in the active universe:
  1. Trend Template (gate — must pass for any setup to be evaluated)
  2. VCP  — Volatility Contraction Pattern
  3. Darvas Box breakout
  4. Power Play
  5. Breakout (short-range and long-range)
  6. Cup & Handle

To add another setup later:
  Step 1: Create setups/mysetup.py with detect_mysetup(df) -> dict
  Step 2: Add its config class to config.py
  Step 3: Import and call it in scan_stock() below
  Step 4: Add its keys to the returned dict
  Step 5: Add a summary block in print_summary_all()
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from config import CHART_DIR, Indicators
from data.universe import get_symbols
from data.fetcher import (fetch_stock, get_benchmark_symbol,
                          get_benchmark_name, get_benchmark_data, compute_rs)
from indicators.trend_template import check_trend_template
from setups.vcp        import detect_vcp
from setups.darvas     import detect_darvas
from setups.powerplay  import detect_powerplay
from setups.breakout   import detect_breakout
from setups.cup_handle import detect_cup_handle
from output.charts  import plot_vcp_chart, _grade_from_quality
from output.console import print_result
from output.exporter import export_vcp_to_excel, export_all_to_excel

os.makedirs(CHART_DIR, exist_ok=True)


def scan_stock(symbol: str) -> dict:
    fetched = fetch_stock(symbol)
    if fetched["error"]:
        return {"symbol": symbol, "error": fetched["error"]}

    df    = fetched["df"]
    start = fetched["start"]
    end   = fetched["end"]

    current_price = round(float(df["Close"].iloc[-1]), 2)

    trend    = check_trend_template(df)
    bm_sym   = get_benchmark_symbol(symbol)
    bm_name  = get_benchmark_name(symbol)
    bm_df    = get_benchmark_data(bm_sym, start, end)
    rs_value = compute_rs(symbol, df, bm_df)

    vcp    = detect_vcp(df, swing_n=Indicators.SWING_LOOKBACK)
    darvas = detect_darvas(df)
    pp     = detect_powerplay(df, symbol=symbol)
    bo     = detect_breakout(df, symbol=symbol)
    ch     = detect_cup_handle(df, symbol=symbol)

    if not trend["all_pass"]:
        vcp["is_vcp"]       = False
        darvas["is_darvas"] = False
        pp["is_powerplay"]  = False
        bo["is_breakout"]   = False
        ch["is_cup_handle"] = False
        if vcp["vcp_quality"] not in ("none", "Fail"):
            vcp["vcp_quality"] = "Filtered (trend template failed)"

    if vcp["is_vcp"]:
        safe  = symbol.replace(".", "_").replace("/", "_")
        grade = _grade_from_quality(vcp["vcp_quality"])
        fname = f"{grade}_{safe}_{vcp.get('vcp_score', 0)}pts.png"
        fpath = os.path.join(CHART_DIR, fname)
        try:
            plot_vcp_chart(symbol, df, vcp, trend, rs_value, fpath)
            print(f"  Chart -> {fpath}")
        except Exception as e:
            print(f"  Chart error for {symbol}: {e}")

    return {
        "symbol"               : symbol,
        "current_price"        : current_price,
        "error"                : None,
        "trend_pass"           : trend["all_pass"],
        "ma50"                 : trend["ma50"],
        "ma150"                : trend["ma150"],
        "ma200"                : trend["ma200"],
        "pct_above_52w_low"    : trend["pct_above_52w_low"],
        "pct_below_52w_high"   : trend["pct_below_52w_high"],
        "down_from_52w_high"   : round(trend["pct_below_52w_high"], 1),
        "within_5pct_high"     : trend["pct_below_52w_high"] <= 5,
        "ema_10"               : round(float(df["EMA_10"].iloc[-1]),  2),
        "ema_20"               : round(float(df["EMA_20"].iloc[-1]),  2),
        "ema_50"               : round(float(df["EMA_50"].iloc[-1]),  2),
        "ema_150"              : round(float(df["EMA_150"].iloc[-1]), 2),
        "ema_200"              : round(float(df["EMA_200"].iloc[-1]), 2),
        "rs"                   : rs_value,
        "rs_index"             : bm_name,
        # VCP
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
        "vcp_score_bonus"      : 1 if trend["pct_below_52w_high"] <= 5 else 0,
        # Darvas
        "is_darvas"            : darvas["is_darvas"],
        "darvas_box_top"       : darvas.get("box_top"),
        "darvas_box_bottom"    : darvas.get("box_bottom"),
        "darvas_box_range"     : darvas.get("box_range_pct"),
        "darvas_box_weeks"     : darvas.get("box_weeks"),
        "darvas_score"         : darvas.get("darvas_score"),
        "darvas_notes"         : darvas.get("notes"),
        # Power Play
        "is_powerplay"         : pp["is_powerplay"],
        "powerplay_score"      : pp.get("powerplay_score"),
        "pp_fund_available"    : pp.get("fundamentals_available"),
        "powerplay_notes"      : pp.get("notes"),
        # Breakout
        "is_breakout"          : bo["is_breakout"],
        "breakout_type"        : bo.get("breakout_type"),
        "breakout_base_days"   : bo.get("base_days"),
        "breakout_base_weeks"  : bo.get("base_weeks"),
        "breakout_resistance"  : bo.get("resistance"),
        "breakout_score"       : bo.get("breakout_score"),
        "breakout_notes"       : bo.get("notes"),
        # Cup & Handle
        "is_cup_handle"        : ch["is_cup_handle"],
        "ch_cup_weeks"         : ch.get("cup_weeks"),
        "ch_cup_depth"         : ch.get("cup_depth"),
        "ch_pivot"             : ch.get("pivot_price"),
        "ch_handle_days"       : ch.get("handle_days"),
        "ch_score"             : ch.get("ch_score"),
        "ch_notes"             : ch.get("notes"),
    }


def print_summary_all(results: list) -> None:
    def cur(s): return "Rs." if s.endswith(".NS") else "$"
    def hdr(label):
        print(f"\n  {'─'*56}\n  {label}\n  {'─'*56}")

    total       = len(results)
    trend_pass  = [r for r in results if r.get("trend_pass")]
    vcp_pass    = [r for r in results if r.get("is_vcp")]
    darvas_pass = [r for r in results if r.get("is_darvas")]
    pp_pass     = [r for r in results if r.get("is_powerplay")]
    bo_pass     = [r for r in results if r.get("is_breakout")]
    ch_pass     = [r for r in results if r.get("is_cup_handle")]

    print("\n" + "=" * 60)
    print("  SCAN SUMMARY")
    print("=" * 60)
    print(f"  Stocks scanned          : {total}")
    print(f"  Trend Template passed   : {len(trend_pass)}")
    print(f"  VCP setups              : {len(vcp_pass)}")
    print(f"  Darvas Box setups       : {len(darvas_pass)}")
    print(f"  Power Play setups       : {len(pp_pass)}")
    print(f"  Breakout setups         : {len(bo_pass)}")
    print(f"  Cup & Handle setups     : {len(ch_pass)}")

    if vcp_pass:
        hdr("VCP SETUPS")
        for r in sorted(vcp_pass, key=lambda x: -(x.get("vcp_score") or 0)):
            print(f"  {r['symbol']:20s}  {cur(r['symbol'])}{r['current_price']}  "
                  f"Pivot: {cur(r['symbol'])}{r['pivot_price']}  "
                  f"Grade: {str(r['vcp_quality'])[:1]}  Score: {r.get('vcp_score')}/11")

    if darvas_pass:
        hdr("DARVAS BOX SETUPS")
        for r in sorted(darvas_pass, key=lambda x: -(x.get("darvas_score") or 0)):
            print(f"  {r['symbol']:20s}  {cur(r['symbol'])}{r['current_price']}  "
                  f"Box: {cur(r['symbol'])}{r['darvas_box_bottom']}--{cur(r['symbol'])}{r['darvas_box_top']}  "
                  f"Score: {r.get('darvas_score')}/12")

    if pp_pass:
        hdr("POWER PLAY SETUPS")
        for r in sorted(pp_pass, key=lambda x: -(x.get("powerplay_score") or 0)):
            print(f"  {r['symbol']:20s}  {cur(r['symbol'])}{r['current_price']}  "
                  f"Score: {r.get('powerplay_score')}/14")

    if bo_pass:
        hdr("BREAKOUT SETUPS")
        for r in sorted(bo_pass, key=lambda x: -(x.get("breakout_score") or 0)):
            btype = r.get("breakout_type", "")
            ref = (f"{r.get('breakout_base_days')}d base" if btype == "short"
                   else f"{r.get('breakout_base_weeks')}w base")
            print(f"  {r['symbol']:20s}  {cur(r['symbol'])}{r['current_price']}  "
                  f"Type: {btype:5s}  {ref}  "
                  f"Resistance: {cur(r['symbol'])}{r.get('breakout_resistance')}  "
                  f"Score: {r.get('breakout_score')}/16")

    if ch_pass:
        hdr("CUP & HANDLE SETUPS")
        for r in sorted(ch_pass, key=lambda x: -(x.get("ch_score") or 0)):
            print(f"  {r['symbol']:20s}  {cur(r['symbol'])}{r['current_price']}  "
                  f"Cup: {r.get('ch_cup_weeks')}w depth {r.get('ch_cup_depth')}%  "
                  f"Pivot: {cur(r['symbol'])}{r.get('ch_pivot')}  "
                  f"Score: {r.get('ch_score')}/17")

    if not any([vcp_pass, darvas_pass, pp_pass, bo_pass, ch_pass]):
        print("\n  No setups found in this scan.")


def run_scanner():
    stocks = get_symbols()
    print("=" * 60)
    print("  Minervini Stock Scanner — All Setups")
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

    print_summary_all(results)
    #export_vcp_to_excel(results)
    export_all_to_excel(results)
    return results


if __name__ == "__main__":
    run_scanner()
