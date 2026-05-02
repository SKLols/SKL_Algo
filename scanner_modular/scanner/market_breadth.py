#!/usr/bin/env python3
"""
market_breadth.py — Standalone market health check.

Runs the Trend Template across the full stock universe and reports
how many stocks are in a Stage 2 uptrend. Use this every morning
before running the main scanner to decide if conditions favour setups.

Output example:
  Market Breadth — 2025-05-02
  ──────────────────────────────────────────────────────────
  S&P 500  |  Stocks scanned: 503  |  Passing: 312  (62.0%)
  Condition: HEALTHY — setups are high-probability

Usage:
    python market_breadth.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from datetime import datetime

from config import MarketBreadth, Data
from data.universe import get_symbols
from data.fetcher import fetch_stock
from indicators.trend_template import check_trend_template
from output.exporter import export_breadth_to_excel


def run_breadth_check() -> dict:
    """
    Scan the full universe for Trend Template compliance.

    Returns a summary dict with counts and condition label,
    and writes per-stock detail to Excel.
    """
    stocks = get_symbols()
    today  = datetime.today().strftime("%Y-%m-%d")

    print("=" * 60)
    print(f"  Market Breadth Check — {today}")
    print(f"  Universe : {len(stocks)} stocks")
    print("=" * 60)

    passed_rows  = []
    breadth_rows = []

    for i, symbol in enumerate(stocks, 1):
        print(f"  [{i:4d}/{len(stocks)}] {symbol:20s}", end="\r")

        fetched = fetch_stock(symbol)
        if fetched["error"]:
            breadth_rows.append({
                "Symbol": symbol,
                "Trend_Pass": False,
                "Error": fetched["error"],
            })
            continue

        df    = fetched["df"]
        trend = check_trend_template(df)

        row = {
            "Symbol"            : symbol,
            "Trend_Pass"        : trend["all_pass"],
            "Price"             : round(float(df["Close"].iloc[-1]), 2),
            "MA50"              : trend["ma50"],
            "MA150"             : trend["ma150"],
            "MA200"             : trend["ma200"],
            "Pct_Above_52w_Low" : trend["pct_above_52w_low"],
            "Pct_Below_52w_High": trend["pct_below_52w_high"],
            "Price_Above_MA50"  : trend["price_above_ma50"],
            "Price_Above_MA150" : trend["price_above_ma150"],
            "Price_Above_MA200" : trend["price_above_ma200"],
            "MA50_gt_MA150"     : trend["ma50_gt_ma150"],
            "MA150_gt_MA200"    : trend["ma150_gt_ma200"],
            "MA200_Rising"      : trend["ma200_rising"],
            "Above_52w_Low_30pct"   : trend["above_52w_low_30pct"],
            "Within_52w_High_25pct" : trend["within_52w_high_25pct"],
            "Error"             : None,
        }
        breadth_rows.append(row)
        if trend["all_pass"]:
            passed_rows.append(row)

    # ── Summary ──
    total   = len(breadth_rows)
    passing = len(passed_rows)
    pct     = 100.0 * passing / total if total > 0 else 0.0

    if pct >= MarketBreadth.BULL_THRESHOLD_PCT or passing >= MarketBreadth.BULL_THRESHOLD:
        condition = MarketBreadth.LABEL_BULL
    elif pct >= MarketBreadth.BULL_THRESHOLD_PCT * 0.5:
        condition = MarketBreadth.LABEL_NEUTRAL
    else:
        condition = MarketBreadth.LABEL_BEAR

    print("\n" + "=" * 60)
    print(f"  Market Breadth — {today}")
    print("─" * 60)
    print(f"  Stocks scanned : {total}")
    print(f"  Passing trend  : {passing}  ({pct:.1f}%)")
    print(f"  Condition      : {condition}")
    print("=" * 60)

    # ── Condition breakdown: how many failed each individual condition ──
    bool_cols = [
        "Price_Above_MA50", "Price_Above_MA150", "Price_Above_MA200",
        "MA50_gt_MA150", "MA150_gt_MA200", "MA200_Rising",
        "Above_52w_Low_30pct", "Within_52w_High_25pct",
    ]
    print("\n  Condition breakdown (failed count):")
    for col in bool_cols:
        failed = sum(1 for r in breadth_rows
                     if r.get(col) is False and r.get("Error") is None)
        print(f"    {col:35s}: {failed} failed / {total}")

    # ── Export ──
    export_breadth_to_excel(breadth_rows)

    return {
        "date"     : today,
        "total"    : total,
        "passing"  : passing,
        "pct"      : round(pct, 1),
        "condition": condition,
        "rows"     : breadth_rows,
    }


if __name__ == "__main__":
    run_breadth_check()
