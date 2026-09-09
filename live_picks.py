#!/usr/bin/env python3
"""
live_picks.py — Today's top-10 stock picks from the three backtested
top-3-sector selection strategies, sent to Telegram as a separate, distinct
alert from the original scanner.py/scheduler.py pipeline (which keeps
sending its own message + vcp_scan_results.xlsx, untouched).

Backtested over Jan-Aug 2026 (see backtest.py, CASE_METHOD_FILTER), each
week first ranks sectors (yfinance `industry` field) by mean Relative
Strength and keeps only stocks in the top 3, then applies one of:
  - top_sector_all_methods     : any of VCP(A/B)/Darvas/PowerPlay/Breakout
                                  qualifies, scored by RS + a bonus per extra
                                  method that also flagged the stock (110
                                  trades over 30 weeks, +1.43% / alpha +9.33pp)
  - top_sector_vcp_only        : must be a VCP (grade A/B) qualifier, scored
                                  by RS alone (79 trades, -2.52% / alpha +5.38pp)
  - top_sector_powerplay_only  : must be a Power Play qualifier, scored by RS
                                  alone (best P&L/alpha/win-rate of the three,
                                  but only 14 trades over 30 weeks - a thin
                                  sample, treat as promising not proven)
Each is capped at the top 10 candidates per scan.

This reuses backtest.py's already-validated scan/scoring engine (same trend
template, same 4 setup detectors, same sector ranking, same Darvas
loosening, same RS scoring) for TODAY instead of a historical Friday. It is
a live watchlist only — it does NOT place or simulate trades.

Usage:
    python live_picks.py                # scan, save Excel, send to Telegram
    python live_picks.py --no-telegram  # scan + save Excel only
    python live_picks.py --date 2026-09-05   # scan as-of a specific date (testing)
"""
import os
import sys
import argparse
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))

from config import OUTPUT_DIR, Benchmark, Indicators
from data.universe import get_symbols
import telegram_config
from telegram_notifier import TelegramNotifier

from backtest import (
    build_sector_map, scan_one_stock, rank_sectors, build_candidate_pool,
    TOP_SECTOR_COUNT, TOP_N_PER_WEEK,
)

LIVE_CASES = ["top_sector_all_methods", "top_sector_vcp_only", "top_sector_powerplay_only"]
OUTPUT_XLSX = os.path.join(OUTPUT_DIR, "live_picks.xlsx")


def get_live_benchmark_df(scan_date: pd.Timestamp) -> pd.DataFrame:
    """Fresh Nifty 50 download covering the RS lookback window up to scan_date."""
    start = scan_date - timedelta(days=int(Indicators.RS_LOOKBACK_DAYS * 1.6) + 30)
    end = scan_date + timedelta(days=1)
    df = yf.download(Benchmark.SYMBOLS["NSE"], start=start, end=end, progress=False, auto_adjust=True)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)
    return df.dropna(subset=["Close"])


def run_live_scan(scan_date: pd.Timestamp):
    universe = get_symbols()
    print(f"Scanning {len(universe)} stocks as of {scan_date.date()}...")

    sector_map = build_sector_map(universe)
    rs_bm_df = get_live_benchmark_df(scan_date)

    scan_results, errors = {}, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(scan_one_stock, s, scan_date, rs_bm_df): s for s in universe}
        for fut in as_completed(futures):
            sym = futures[fut]
            try:
                r = fut.result()
            except Exception as e:
                r = {"symbol": sym, "error": str(e)}
            if r.get("error"):
                errors += 1
            else:
                scan_results[sym] = r
    print(f"  Downloaded OK: {len(scan_results)}/{len(universe)}  (errors: {errors})")

    top_sectors = rank_sectors(scan_results, sector_map)
    print(f"  Top {TOP_SECTOR_COUNT} sectors today: "
          + ", ".join(f"{s} (RS {rs:+.1f}, n={n})" for s, rs, n in top_sectors[:TOP_SECTOR_COUNT]))

    picks = {}
    for case in LIVE_CASES:
        pool = build_candidate_pool(scan_results, sector_map, case, top_sectors)
        picks[case] = pool[:TOP_N_PER_WEEK]
        print(f"  {case}: {len(pool)} candidates, top {len(picks[case])} selected")

    return picks, scan_results, top_sectors


def build_picks_dataframe(pool: list, scan_results: dict) -> pd.DataFrame:
    rows = []
    for rank, cand in enumerate(pool, start=1):
        sym = cand["symbol"]
        r = scan_results[sym]
        method_detail = []
        for m in cand["matched_methods"]:
            meta = r["methods"][m]
            label = m
            if meta.get("grade"):
                label += f"({meta['grade']})"
            method_detail.append(label)
        rows.append({
            "rank": rank, "symbol": sym, "current_price": round(r["entry_price"], 2),
            "matched_methods": ", ".join(method_detail), "num_methods": len(cand["matched_methods"]),
            "rs": cand["rs"], "sector": cand["sector"], "score": cand["score"],
        })
    return pd.DataFrame(rows)


def build_live_excel(picks: dict, scan_results: dict, top_sectors: list, scan_date: pd.Timestamp) -> str:
    df_sectors = pd.DataFrame(
        [{"rank": i + 1, "sector": s, "mean_rs": round(rs, 2), "num_stocks": n}
         for i, (s, rs, n) in enumerate(top_sectors[:TOP_SECTOR_COUNT])]
    )

    with pd.ExcelWriter(OUTPUT_XLSX, engine="openpyxl") as writer:
        df_sectors.to_excel(writer, index=False, sheet_name="Top Sectors")
        for case in LIVE_CASES:
            df = build_picks_dataframe(picks[case], scan_results)
            df.to_excel(writer, index=False, sheet_name=case)

    print(f"  Excel saved -> {OUTPUT_XLSX}")
    return OUTPUT_XLSX


def build_telegram_message(picks: dict, top_sectors: list, scan_date: pd.Timestamp) -> str:
    lines = [f"<b>Daily Stock Picks - {scan_date.strftime('%Y-%m-%d')}</b>", ""]
    lines.append("<b>Top sectors today:</b>")
    for s, rs, n in top_sectors[:TOP_SECTOR_COUNT]:
        lines.append(f"  - {s} (RS {rs:+.1f}, n={n})")
    lines.append("")

    for case in LIVE_CASES:
        pool = picks[case]
        lines.append(f"<b>{case}</b> ({len(pool)} picks):")
        if not pool:
            lines.append("  (no candidates today)")
        for cand in pool:
            lines.append(f"  <code>{cand['symbol']:15s}</code> RS {cand['rs']:+.1f}  "
                          f"[{','.join(cand['matched_methods'])}]  score {cand['score']:.1f}")
        lines.append("")

    lines.append("<i>Full detail in the attached Excel file. Watchlist only - not an executed trade.</i>")
    return "\n".join(lines)


def send_to_telegram(excel_path: str, picks: dict, top_sectors: list, scan_date: pd.Timestamp) -> None:
    notifier = TelegramNotifier(telegram_config.TELEGRAM_BOT_TOKEN, telegram_config.TELEGRAM_CHAT_ID)
    message = build_telegram_message(picks, top_sectors, scan_date)
    if notifier.send_message(message):
        print("  Telegram message sent")
    else:
        print("  Telegram message FAILED")
    caption = f"Daily stock picks - {scan_date.strftime('%Y-%m-%d')}"
    if notifier.send_file(excel_path, caption):
        print("  Telegram file sent")
    else:
        print("  Telegram file FAILED")


def generate_and_send(scan_date: pd.Timestamp | None = None, send_telegram: bool = True) -> str:
    """
    Run the live scan, save the Excel, and (unless send_telegram=False) push
    it to Telegram. Single entry point used by both the CLI below and
    scheduler.py's automated daily job. Returns the Excel file path.
    """
    if scan_date is None:
        scan_date = pd.Timestamp(datetime.now().date())

    picks, scan_results, top_sectors = run_live_scan(scan_date)
    excel_path = build_live_excel(picks, scan_results, top_sectors, scan_date)

    if send_telegram:
        send_to_telegram(excel_path, picks, top_sectors, scan_date)
    else:
        print("  Skipping Telegram (send_telegram=False)")

    return excel_path


def main():
    parser = argparse.ArgumentParser(description="Live top-10 stock picks (top_sector_all_methods / top_sector_vcp_only / top_sector_powerplay_only)")
    parser.add_argument("--no-telegram", action="store_true", help="skip sending to Telegram")
    parser.add_argument("--date", type=str, default=None,
                         help="scan as-of this date (YYYY-MM-DD) instead of today, for testing")
    args = parser.parse_args()

    scan_date = pd.Timestamp(args.date) if args.date else None
    generate_and_send(scan_date=scan_date, send_telegram=not args.no_telegram)


if __name__ == "__main__":
    main()
