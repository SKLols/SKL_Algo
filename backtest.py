#!/usr/bin/env python3
"""
backtest.py — Multi-setup weekly-scan paper-trading backtest engine.

Simulates the existing Minervini Trend Template gate (indicators/trend_template.py)
combined with FOUR existing setup detectors — VCP, Darvas Box, Power Play, and
Breakout (setups/vcp.py, setups/darvas.py, setups/powerplay.py, setups/breakout.py)
— run every Friday from 1 Jan 2026 through 30 Jul 2026. Each method is paper-traded
as its own independent strategy so their results can be compared head-to-head.

VCP only buys Grade A/B setups (Grade C/D are scanned but skipped — see
VCP_ALLOWED_GRADES). The other three methods have no letter-grade concept in
their source modules, so they gate on their own is_darvas/is_powerplay/is_breakout
flag only.

Each qualifying position is bought at that Friday's close and walked forward
day-by-day through 31 Aug 2026 with:
  - a 10% stop-loss (LOW-based trigger, exit at CLOSE)
  - +20% -> sell 50%, +40% -> sell 50% of what's left (HIGH-based triggers)
  - a RATCHETING stop: once PT1 fires the stop for the remainder moves up to
    breakeven (entry price); once PT2 fires it moves up again to the PT1 price.
    This protects locked-in gains instead of leaving the whole position exposed
    to the original 10% stop for its entire life.
  - a hard close on 31 Aug 2026 for anything still open, at any P&L.

Two re-entry policies are run side-by-side for every method, as two separate
analyses:
  - "reentry_always"      — a symbol may be bought again on a later Friday even
                             while an earlier position in it is still open
                             (no de-duplication — this is what the previous
                             version of this script always did).
  - "reentry_after_close" — a symbol already holding an open position is
                             skipped; it becomes buyable again only once that
                             earlier position has fully exited (SL or hard
                             close), then re-qualifies like any other stock.

That gives 4 methods x 2 policies = 8 independent trade books, all sharing the
same weekly scan data and exit-price downloads (each stock is still downloaded
only once per week no matter how many method/policy combinations act on it).

Does not modify any existing module. data/fetcher.fetch_stock() always anchors
its download to datetime.today(), so it cannot be reused for a historical
"as-of" scan — fetch_stock_asof() and fetch_price_history() below reimplement
its download/clean pipeline for an arbitrary historical date, reusing
add_ema_columns() from data/fetcher.py for the parts that are identical.

Usage:
    python backtest.py --mode fetch_test   # Step 1: single-stock/date sanity check (AAPL)
    python backtest.py --mode exit_test    # Step 2: exit-logic day-by-day walkthrough (AAPL)
    python backtest.py --mode mini_scan    # Step 3: 10-stock scan, first scan Friday only
    python backtest.py --mode full         # Step 4: full NSE 500, every scan Friday
    python backtest.py --mode full --no-resume   # ignore checkpoint, start over
"""
import os
import sys
import json
import math
import argparse
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

import numpy as np
import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))

from config import OUTPUT_DIR, Data, Benchmark, Indicators
from data.universe import get_symbols
from data.fetcher import add_ema_columns, get_benchmark_data
from indicators.trend_template import check_trend_template
from setups.vcp import detect_vcp
from setups.darvas import detect_darvas
from setups.powerplay import detect_powerplay
from setups.breakout import detect_breakout

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ─────────────────────────────────────────────
# CONSTANTS
# ─────────────────────────────────────────────
SCAN_FRIDAYS = list(pd.date_range("2026-01-01", "2026-07-30", freq="W-FRI"))
HOLD_END_DATE   = pd.Timestamp("2026-08-31")     # hard close date (inclusive)
BENCHMARK_START = pd.Timestamp("2026-01-01")

POSITION_SIZE = 10_000.0
SL_MULT  = 0.90
PT1_MULT = 1.20
PT2_MULT = 1.40

METHODS  = ["VCP", "Darvas", "PowerPlay", "Breakout"]
POLICIES = ["reentry_always", "reentry_after_close"]
VCP_ALLOWED_GRADES = {"A", "B"}   # VCP only buys these grades; C/D are scanned but skipped

RESULTS_XLSX    = os.path.join(OUTPUT_DIR, "backtest_results.xlsx")
CHECKPOINT_JSON = os.path.join(OUTPUT_DIR, "backtest_checkpoint.json")

TEST_STOCK     = "AAPL"
MINI_SCAN_SIZE = 10

TRADE_COLS = [
    "method", "policy", "symbol", "scan_date", "entry_date", "entry_price", "shares", "position_value",
    "grade", "score", "pivot_price",
    "exit_1_date", "exit_1_price", "exit_1_shares", "exit_1_reason",
    "exit_2_date", "exit_2_price", "exit_2_shares", "exit_2_reason",
    "exit_3_date", "exit_3_price", "exit_3_shares", "exit_3_reason",
    "total_pnl_dollars", "total_pnl_pct", "exit_reason_summary",
]

EXIT_CATEGORIES = ["SL", "PT1_only", "PT1_PT2", "PT1_PT2_held", "full_held"]


# ─────────────────────────────────────────────
# DATE HELPERS
# ─────────────────────────────────────────────
def _next_business_day(date: pd.Timestamp) -> pd.Timestamp:
    d = pd.Timestamp(date) + timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def new_state() -> dict:
    """Empty trade ledger: state[method][policy] -> list of trade records."""
    return {m: {p: [] for p in POLICIES} for m in METHODS}


# ─────────────────────────────────────────────
# DATA DOWNLOAD  (as-of historical variants of data/fetcher.py's logic)
# ─────────────────────────────────────────────
def fetch_stock_asof(symbol: str, end_date: pd.Timestamp) -> dict:
    """
    Same cleaning pipeline as data/fetcher.fetch_stock(), anchored to a fixed
    historical `end_date` instead of datetime.today() so the scan never sees
    data beyond the simulated scan date. Reuses add_ema_columns().
    """
    end_date = pd.Timestamp(end_date)
    download_end = _next_business_day(end_date)   # yfinance end= is exclusive
    start = end_date - timedelta(days=Data.LOOKBACK_DAYS + Data.MA_WARMUP_BUFFER)

    try:
        df = yf.download(symbol, start=start, end=download_end,
                          progress=False, auto_adjust=True)
    except Exception as e:
        return {"df": None, "error": str(e)}

    if df.empty or len(df) < 60:
        return {"df": None, "error": "Insufficient data"}

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]
    df = df[df.index <= end_date]      # hard guarantee against any look-ahead

    if df.empty or len(df) < 60:
        return {"df": None, "error": "Insufficient data after cleaning"}

    df = add_ema_columns(df)
    return {"df": df, "error": None}


def fetch_price_history(symbol: str, start_date: pd.Timestamp, end_date: pd.Timestamp) -> dict:
    """One batch OHLCV download for exit-path simulation. end_date is inclusive."""
    download_end = pd.Timestamp(end_date) + timedelta(days=1)
    try:
        df = yf.download(symbol, start=start_date, end=download_end,
                          progress=False, auto_adjust=True)
    except Exception as e:
        return {"df": None, "error": str(e)}

    if df.empty:
        return {"df": None, "error": "No data"}

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["Close"])
    if df.empty:
        return {"df": None, "error": "No data after cleaning"}

    return {"df": df, "error": None}


# ─────────────────────────────────────────────
# SCAN LOGIC — trend template gate + all 4 setup detectors
# ─────────────────────────────────────────────
def scan_one_stock(symbol: str, scan_date: pd.Timestamp) -> dict:
    """
    Run the trend-template gate plus VCP/Darvas/PowerPlay/Breakout detection
    as-of scan_date, one download shared by all 4 methods. Never raises.
    """
    try:
        fetched = fetch_stock_asof(symbol, scan_date)
        if fetched["error"]:
            return {"symbol": symbol, "error": fetched["error"]}

        df = fetched["df"]
        trend_pass = bool(check_trend_template(df)["all_pass"])

        vcp    = detect_vcp(df, swing_n=Indicators.SWING_LOOKBACK)
        darvas = detect_darvas(df)
        pp     = detect_powerplay(df, symbol=symbol)
        bo     = detect_breakout(df, symbol=symbol)

        vcp_grade = vcp["vcp_quality"][0] if vcp["is_vcp"] else None

        methods = {
            "VCP": {
                "qualifies": trend_pass and bool(vcp["is_vcp"]) and vcp_grade in VCP_ALLOWED_GRADES,
                "grade": vcp_grade, "score": vcp.get("vcp_score"), "pivot_price": vcp.get("pivot_price"),
            },
            "Darvas": {
                "qualifies": trend_pass and bool(darvas.get("is_darvas")),
                "grade": None, "score": darvas.get("darvas_score"), "pivot_price": darvas.get("box_top"),
            },
            "PowerPlay": {
                "qualifies": trend_pass and bool(pp.get("is_powerplay")),
                "grade": None, "score": pp.get("powerplay_score"), "pivot_price": None,
            },
            "Breakout": {
                "qualifies": trend_pass and bool(bo.get("is_breakout")),
                "grade": bo.get("breakout_type"), "score": bo.get("breakout_score"),
                "pivot_price": bo.get("resistance"),
            },
        }

        return {
            "symbol": symbol, "error": None,
            "entry_date": df.index[-1], "entry_price": float(df["Close"].iloc[-1]),
            "methods": methods,
        }
    except Exception as e:
        return {"symbol": symbol, "error": f"{type(e).__name__}: {e}"}


# ─────────────────────────────────────────────
# EXIT SIMULATION
# ─────────────────────────────────────────────
def simulate_exit(shares: int, entry_price: float, entry_date: pd.Timestamp,
                   price_df: pd.DataFrame, hard_close_date: pd.Timestamp) -> list:
    """
    Walk price_df day-by-day, starting the day AFTER entry_date (entry already
    happened at that Friday's close), applying:
      SL  @ a RATCHETING stop (LOW-based) -> exit ALL remaining shares at CLOSE
            starts at entry*SL_MULT; moves to entry price once PT1 fires;
            moves to the PT1 price once PT2 fires. Protects banked gains
            instead of leaving the whole position exposed to the original stop.
      PT1 @ entry*1.20 (HIGH-based) -> sell 50% of the ORIGINAL shares at CLOSE
      PT2 @ entry*1.40 (HIGH-based) -> sell 50% of what's left at CLOSE
    Same-day priority: SL > PT1 > PT2 (only one trigger processed per day).
    Any shares still open at hard_close_date are closed there regardless of P&L.
    Returns an ordered list of {date, price, shares, reason} events (reason in
    SL/PT1/PT2/EOD), at most 3 events.
    """
    sl_price  = entry_price * SL_MULT   # ratchets up as targets are hit
    pt1_price = entry_price * PT1_MULT
    pt2_price = entry_price * PT2_MULT

    df = price_df[(price_df.index > entry_date) & (price_df.index <= hard_close_date)].sort_index()

    remaining = shares
    stage = 0   # 0 = nothing hit yet, 1 = PT1 done, 2 = PT2 done
    events = []

    for date, row in df.iterrows():
        if remaining <= 0:
            break
        low, high, close = float(row["Low"]), float(row["High"]), float(row["Close"])

        if low < sl_price:
            events.append({"date": date, "price": close, "shares": remaining, "reason": "SL"})
            remaining = 0
            break
        elif stage == 0 and high > pt1_price:
            qty = min(shares // 2 or remaining, remaining)
            events.append({"date": date, "price": close, "shares": qty, "reason": "PT1"})
            remaining -= qty
            stage = 1
            sl_price = entry_price     # ratchet stop to breakeven
        elif stage == 1 and high > pt2_price:
            qty = min(remaining // 2 or remaining, remaining)
            events.append({"date": date, "price": close, "shares": qty, "reason": "PT2"})
            remaining -= qty
            stage = 2
            sl_price = pt1_price       # ratchet stop to the PT1 price

    if remaining > 0:
        if len(df) > 0 and df.index[-1] == hard_close_date:
            close_price, close_date = float(df.loc[hard_close_date, "Close"]), hard_close_date
        elif len(df) > 0:
            close_price, close_date = float(df["Close"].iloc[-1]), df.index[-1]
        else:
            close_price, close_date = entry_price, entry_date
        events.append({"date": close_date, "price": close_price, "shares": remaining, "reason": "EOD"})

    return events


def classify_exit_summary(events: list) -> str:
    reasons = [e["reason"] for e in events]
    has_sl, has_pt1, has_pt2 = "SL" in reasons, "PT1" in reasons, "PT2" in reasons

    if has_sl and not has_pt1:
        return "SL"
    if has_pt1 and has_pt2:
        return "PT1_PT2" if has_sl else "PT1_PT2_held"
    if has_pt1 and not has_pt2:
        return "PT1_only"
    return "full_held"


def build_trade_record(symbol: str, method: str, policy: str, scan_date: pd.Timestamp,
                        ec: dict, meta: dict) -> dict:
    entry_price = ec["entry_price"]
    entry_date  = ec["entry_date"]
    shares      = ec["shares"]
    events      = ec["events"]
    position_value = round(entry_price * shares, 2)

    proceeds    = sum(e["shares"] * e["price"] for e in events)
    pnl_dollars = round(proceeds - position_value, 2)
    pnl_pct     = round(100 * pnl_dollars / position_value, 2) if position_value else 0.0

    slots = (events + [None, None, None])[:3]

    def slot(i, field):
        e = slots[i]
        if e is None:
            return None
        return round(e[field], 2) if field == "price" else e[field]

    return {
        "method": method, "policy": policy,
        "symbol": symbol, "scan_date": scan_date, "entry_date": entry_date,
        "entry_price": round(entry_price, 2), "shares": shares, "position_value": position_value,
        "grade": meta.get("grade"), "score": meta.get("score"), "pivot_price": meta.get("pivot_price"),
        "exit_1_date": slot(0, "date"), "exit_1_price": slot(0, "price"),
        "exit_1_shares": slot(0, "shares"), "exit_1_reason": slot(0, "reason"),
        "exit_2_date": slot(1, "date"), "exit_2_price": slot(1, "price"),
        "exit_2_shares": slot(1, "shares"), "exit_2_reason": slot(1, "reason"),
        "exit_3_date": slot(2, "date"), "exit_3_price": slot(2, "price"),
        "exit_3_shares": slot(2, "shares"), "exit_3_reason": slot(2, "reason"),
        "total_pnl_dollars": pnl_dollars, "total_pnl_pct": pnl_pct,
        "exit_reason_summary": classify_exit_summary(events),
        "final_exit_date": events[-1]["date"] if events else entry_date,
    }


def summarize_week(scan_date: pd.Timestamp, method: str, policy: str,
                    qualifiers: list, new_trades: list) -> dict:
    total_deployed = round(sum(t["position_value"] for t in new_trades), 2)
    portfolio_value = round(sum(
        (t["exit_1_price"] or 0) * (t["exit_1_shares"] or 0) +
        (t["exit_2_price"] or 0) * (t["exit_2_shares"] or 0) +
        (t["exit_3_price"] or 0) * (t["exit_3_shares"] or 0)
        for t in new_trades), 2)
    pnl_dollars = round(portfolio_value - total_deployed, 2)
    pnl_pct     = round(100 * pnl_dollars / total_deployed, 2) if total_deployed else 0.0
    return {
        "scan_date": scan_date, "method": method, "policy": policy,
        "stocks_flagged": len(qualifiers), "stocks_bought": len(new_trades),
        "total_deployed": total_deployed, "portfolio_value_apr30": portfolio_value,
        "pnl_dollars": pnl_dollars, "pnl_pct": pnl_pct,
    }


# ─────────────────────────────────────────────
# WEEKLY SCAN RUNNER
# ─────────────────────────────────────────────
def run_friday_scan(scan_date: pd.Timestamp, universe: list, state: dict, verbose: bool = False) -> list:
    """
    Scans the universe once, then independently evaluates all 4 methods x 2
    re-entry policies against that single scan. Each stock's exit trajectory
    is downloaded and simulated only once per week even if multiple
    method/policy combinations decide to buy it. Returns a list of week-row
    dicts, one per (method, policy).
    """
    print(f"\n{'='*70}\n  SCANNING {scan_date.date()}  ({len(universe)} stocks)\n{'='*70}")

    scan_results, errors = {}, 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(scan_one_stock, s, scan_date): s for s in universe}
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

    # Decide the buy list for each of the 8 (method, policy) combinations
    buy_plan = {}
    need_exit_data = set()
    for method in METHODS:
        for policy in POLICIES:
            trades_list = state[method][policy]
            open_syms = set()
            if policy == "reentry_after_close":
                open_syms = {t["symbol"] for t in trades_list if t["final_exit_date"] > scan_date}
            qualifiers = [sym for sym, r in scan_results.items()
                          if r["methods"][method]["qualifies"] and sym not in open_syms]
            buy_plan[(method, policy)] = qualifiers
            need_exit_data.update(qualifiers)

    # Fetch + simulate the exit lifecycle ONCE per symbol needed by any combo
    exit_cache = {}
    skipped_price = 0
    with ThreadPoolExecutor(max_workers=8) as ex:
        futures = {}
        for sym in need_exit_data:
            r = scan_results[sym]
            entry_price = r["entry_price"]
            shares = math.floor(POSITION_SIZE / entry_price) if entry_price > 0 else 0
            if shares <= 0:
                skipped_price += 1
                continue
            fut = ex.submit(fetch_price_history, sym, r["entry_date"], HOLD_END_DATE)
            futures[fut] = (sym, r, shares)

        for fut in as_completed(futures):
            sym, r, shares = futures[fut]
            try:
                fetched = fut.result()
                if fetched["error"]:
                    print(f"    EXIT-DATA ERROR {sym}: {fetched['error']}")
                    continue
                events = simulate_exit(shares, r["entry_price"], r["entry_date"], fetched["df"], HOLD_END_DATE)
                exit_cache[sym] = {"events": events, "shares": shares,
                                    "entry_price": r["entry_price"], "entry_date": r["entry_date"]}
            except Exception as e:
                print(f"    EXIT-SIM ERROR {sym}: {type(e).__name__}: {e}")

    if skipped_price:
        print(f"  Skipped {skipped_price} symbol(s): entry price too high for a Rs.10,000 position")

    week_rows = []
    print(f"\n  --- Week of {scan_date.date()} summary (method / policy) ---")
    for method in METHODS:
        for policy in POLICIES:
            new_trades = []
            for sym in buy_plan[(method, policy)]:
                ec = exit_cache.get(sym)
                if ec is None:
                    continue
                meta = scan_results[sym]["methods"][method]
                new_trades.append(build_trade_record(sym, method, policy, scan_date, ec, meta))
            state[method][policy].extend(new_trades)
            row = summarize_week(scan_date, method, policy, buy_plan[(method, policy)], new_trades)
            week_rows.append(row)
            print(f"    {method:10s} {policy:20s}  flagged={row['stocks_flagged']:3d}  "
                  f"bought={row['stocks_bought']:3d}  deployed=Rs.{row['total_deployed']:>10,.0f}  "
                  f"pnl={row['pnl_pct']:+6.2f}%")
            if verbose:
                for t in new_trades:
                    print(f"        {t['symbol']:15s} grade={t['grade']}  entry={t['entry_price']}  "
                          f"shares={t['shares']}  pnl={t['total_pnl_pct']:+.2f}%  ({t['exit_reason_summary']})")

    return week_rows


# ─────────────────────────────────────────────
# CHECKPOINTING
# ─────────────────────────────────────────────
def _json_default(o):
    if isinstance(o, pd.Timestamp):
        return o.strftime("%Y-%m-%d")
    if isinstance(o, np.integer):
        return int(o)
    if isinstance(o, np.floating):
        return float(o)
    raise TypeError(f"Not JSON serializable: {type(o)}")


def save_checkpoint(completed_fridays: list, state: dict, weekly_rows: list) -> None:
    data = {
        "completed_fridays": [d.strftime("%Y-%m-%d") for d in completed_fridays],
        "state": state,
        "weekly_rows": weekly_rows,
    }
    with open(CHECKPOINT_JSON, "w") as f:
        json.dump(data, f, default=_json_default, indent=2)
    print(f"  Checkpoint saved -> {CHECKPOINT_JSON}")


def load_checkpoint():
    if not os.path.exists(CHECKPOINT_JSON):
        return [], new_state(), []
    with open(CHECKPOINT_JSON) as f:
        data = json.load(f)

    date_fields = ("scan_date", "entry_date", "final_exit_date",
                   "exit_1_date", "exit_2_date", "exit_3_date")

    state = new_state()
    saved_state = data.get("state", {})
    for method in METHODS:
        for policy in POLICIES:
            trades_list = saved_state.get(method, {}).get(policy, [])
            for t in trades_list:
                for k in date_fields:
                    if t.get(k):
                        t[k] = pd.Timestamp(t[k])
            state[method][policy] = trades_list

    weekly_rows = data.get("weekly_rows", [])
    for w in weekly_rows:
        w["scan_date"] = pd.Timestamp(w["scan_date"])

    completed = [pd.Timestamp(d) for d in data.get("completed_fridays", [])]
    return completed, state, weekly_rows


# ─────────────────────────────────────────────
# BENCHMARK
# ─────────────────────────────────────────────
def compute_benchmark() -> float:
    """Nifty 50 (^NSEI) buy-and-hold return from BENCHMARK_START to HOLD_END_DATE close."""
    bm_symbol = Benchmark.SYMBOLS["NSE"]
    download_end = HOLD_END_DATE + timedelta(days=1)
    bm = get_benchmark_data(bm_symbol, BENCHMARK_START, download_end)
    if isinstance(bm.columns, pd.MultiIndex):
        bm.columns = bm.columns.get_level_values(0)
    bm = bm.dropna(subset=["Close"])
    start_price = float(bm["Close"].iloc[0])
    end_price   = float(bm.loc[bm.index <= HOLD_END_DATE, "Close"].iloc[-1])
    return round(100 * (end_price / start_price - 1), 2)


# ─────────────────────────────────────────────
# REPORTING
# ─────────────────────────────────────────────
def overall_totals(trades: list) -> dict:
    """Total money invested vs. total money returned across a set of trades."""
    invested = sum(t["position_value"] for t in trades)
    returned = sum(
        (t["exit_1_price"] or 0) * (t["exit_1_shares"] or 0) +
        (t["exit_2_price"] or 0) * (t["exit_2_shares"] or 0) +
        (t["exit_3_price"] or 0) * (t["exit_3_shares"] or 0)
        for t in trades)
    pnl     = returned - invested
    pnl_pct = 100 * pnl / invested if invested else 0.0
    return {"invested": round(invested, 2), "returned": round(returned, 2),
            "pnl": round(pnl, 2), "pnl_pct": round(pnl_pct, 2)}


def all_trades_flat(state: dict) -> list:
    return [t for method in METHODS for policy in POLICIES for t in state[method][policy]]


def build_comparison_rows(state: dict, spy_pnl_pct: float) -> list:
    rows = []
    for method in METHODS:
        for policy in POLICIES:
            trades = state[method][policy]
            tot = overall_totals(trades)
            win_rate = round(100 * sum(1 for t in trades if t["total_pnl_pct"] > 0) / len(trades), 2) if trades else 0.0
            avg_days = round(sum((t["final_exit_date"] - t["entry_date"]).days for t in trades) / len(trades), 1) if trades else 0.0
            rows.append({
                "method": method, "policy": policy, "trades": len(trades),
                "invested": tot["invested"], "returned": tot["returned"],
                "pnl_dollars": tot["pnl"], "pnl_pct": tot["pnl_pct"],
                "win_rate": win_rate, "avg_days_held": avg_days,
                "nifty50_pct": spy_pnl_pct, "alpha": round(tot["pnl_pct"] - spy_pnl_pct, 2),
            })
    rows.sort(key=lambda r: r["pnl_pct"], reverse=True)
    return rows


def build_excel_report(state: dict, weekly_rows: list, spy_pnl_pct: float):
    trades = all_trades_flat(state)

    comparison_rows = build_comparison_rows(state, spy_pnl_pct)
    df_comparison = pd.DataFrame(comparison_rows)

    df_trades = pd.DataFrame([{k: t.get(k) for k in TRADE_COLS} for t in trades])

    df_weekly = pd.DataFrame([
        {**w, "spy_pnl_pct": spy_pnl_pct, "alpha": round(w["pnl_pct"] - spy_pnl_pct, 2)}
        for w in weekly_rows
    ])

    grade_rows = []
    for method in METHODS:
        for policy in POLICIES:
            sub_all = state[method][policy]
            grade_values = sorted({t["grade"] for t in sub_all if t["grade"] is not None})
            if any(t["grade"] is None for t in sub_all):
                grade_values.append(None)
            for g in grade_values:
                sub = [t for t in sub_all if t["grade"] == g]
                if not sub:
                    continue
                count = len(sub)

                def pct_hit(reason):
                    hits = sum(1 for t in sub
                               if reason in (t["exit_1_reason"], t["exit_2_reason"], t["exit_3_reason"]))
                    return round(100 * hits / count, 2)

                grade_rows.append({
                    "method": method, "policy": policy, "grade": g, "count": count,
                    "avg_pnl_pct": round(sum(t["total_pnl_pct"] for t in sub) / count, 2),
                    "win_rate": round(100 * sum(1 for t in sub if t["total_pnl_pct"] > 0) / count, 2),
                    "avg_days_held": round(sum((t["final_exit_date"] - t["entry_date"]).days for t in sub) / count, 1),
                    "pct_hit_SL": pct_hit("SL"), "pct_hit_PT1": pct_hit("PT1"), "pct_hit_PT2": pct_hit("PT2"),
                })
    df_grade = pd.DataFrame(grade_rows)

    exit_rows = []
    for method in METHODS:
        for policy in POLICIES:
            sub_all = state[method][policy]
            for cat in EXIT_CATEGORIES:
                sub = [t for t in sub_all if t["exit_reason_summary"] == cat]
                count = len(sub)
                avg_pnl = round(sum(t["total_pnl_pct"] for t in sub) / count, 2) if count else 0.0
                label = "full_held_to_apr30" if cat == "full_held" else cat
                exit_rows.append({"method": method, "policy": policy, "exit_reason": label,
                                   "count": count, "avg_pnl_pct": avg_pnl})
    df_exit = pd.DataFrame(exit_rows)

    with pd.ExcelWriter(RESULTS_XLSX, engine="openpyxl") as writer:
        df_comparison.to_excel(writer, index=False, sheet_name="Comparison Summary")
        df_trades.to_excel(writer, index=False, sheet_name="All Trades")
        df_weekly.to_excel(writer, index=False, sheet_name="Weekly Summary")
        df_grade.to_excel(writer, index=False, sheet_name="Grade Analysis")
        df_exit.to_excel(writer, index=False, sheet_name="Exit Analysis")

    print(f"\n  Results saved -> {RESULTS_XLSX}")
    return df_comparison, df_trades, df_weekly, df_grade, df_exit


def print_terminal_summary(state: dict, spy_pnl_pct: float) -> None:
    print("\n" + "=" * 70)
    print(f"  BACKTEST RESULTS - {BENCHMARK_START.date()} to {HOLD_END_DATE.date()}")
    print("=" * 70)

    trades = all_trades_flat(state)
    if not trades:
        print("  No trades were opened.")
        print("=" * 70)
        return

    rows = build_comparison_rows(state, spy_pnl_pct)
    print(f"  Nifty 50 benchmark: {spy_pnl_pct:+.2f}%\n")
    print(f"  {'METHOD':10s} {'POLICY':20s} {'TRADES':>7s} {'INVESTED':>14s} "
          f"{'P&L %':>8s} {'ALPHA':>8s} {'WIN%':>7s}")
    print("  " + "-" * 78)
    for r in rows:
        print(f"  {r['method']:10s} {r['policy']:20s} {r['trades']:7d} "
              f"Rs.{r['invested']:>10,.0f} {r['pnl_pct']:>+7.2f}% {r['alpha']:>+7.2f} {r['win_rate']:>6.1f}%")
    traded_rows = [r for r in rows if r["trades"] > 0]
    if traded_rows:
        best = traded_rows[0]
        print(f"\n  Best combination: {best['method']} / {best['policy']}  "
              f"({best['pnl_pct']:+.2f}% P&L, alpha {best['alpha']:+.2f}pp, {best['trades']} trades)")
    else:
        print("\n  No method opened any trades.")

    print("\n" + "-" * 70)
    print("  MONEY SUMMARY (all methods & policies combined)")
    print("-" * 70)
    tot = overall_totals(trades)
    result_word = "PROFIT" if tot["pnl"] >= 0 else "LOSS"
    print(f"  You invested  : Rs.{tot['invested']:,.2f}")
    print(f"  You got back  : Rs.{tot['returned']:,.2f}")
    print(f"  {result_word:<14}: Rs.{abs(tot['pnl']):,.2f}")
    print(f"  Overall, you {'made' if tot['pnl'] >= 0 else 'lost'} money: "
          f"{tot['pnl_pct']:+.2f}% on your invested capital")
    print("-" * 70)
    print("=" * 70)


# ─────────────────────────────────────────────
# TEST MODES
# ─────────────────────────────────────────────
def test_fetch_single():
    print("STEP 1 - single-stock/date fetch sanity check")
    scan_date = SCAN_FRIDAYS[0]
    print(f"  Symbol: {TEST_STOCK}   Scan date: {scan_date.date()} (must not see anything after this date)")

    fetched = fetch_stock_asof(TEST_STOCK, scan_date)
    if fetched["error"]:
        print(f"  FAILED: {fetched['error']}")
        return
    df = fetched["df"]
    print(f"  Rows downloaded : {len(df)}")
    print(f"  Data range      : {df.index[0].date()} -> {df.index[-1].date()}")
    print(f"  Last row date   : {df.index[-1].date()}  (expected {scan_date.date()})")
    print(f"  Close price     : {df['Close'].iloc[-1]:.2f}")

    ref = yf.download(TEST_STOCK, start=scan_date - timedelta(days=4),
                       end=scan_date + timedelta(days=3), progress=False, auto_adjust=True)
    if isinstance(ref.columns, pd.MultiIndex):
        ref.columns = ref.columns.get_level_values(0)
    print("\n  Independent reference download for cross-check:")
    print(ref[["Close"]].to_string())


def test_exit_single():
    print("STEP 2 - exit-logic day-by-day walkthrough (with ratcheting stop)")
    scan_date = SCAN_FRIDAYS[0]
    scanned = fetch_stock_asof(TEST_STOCK, scan_date)
    if scanned["error"]:
        print(f"  FAILED to get entry price: {scanned['error']}")
        return
    entry_date  = scanned["df"].index[-1]
    entry_price = float(scanned["df"]["Close"].iloc[-1])
    shares      = math.floor(POSITION_SIZE / entry_price)

    fetched = fetch_price_history(TEST_STOCK, entry_date, HOLD_END_DATE)
    if fetched["error"]:
        print(f"  FAILED to get exit data: {fetched['error']}")
        return
    df = fetched["df"]

    pt1, pt2 = entry_price * PT1_MULT, entry_price * PT2_MULT
    sl = entry_price * SL_MULT
    print(f"  Entry {entry_date.date()} @ {entry_price:.2f}   shares={shares}   "
          f"position_value={entry_price*shares:.2f}")
    print(f"  Initial SL < {sl:.2f}   PT1 > {pt1:.2f}   PT2 > {pt2:.2f}")
    print(f"  (stop ratchets to {entry_price:.2f} after PT1, to {pt1:.2f} after PT2)\n")

    stage = 0
    cur_sl = sl
    for date, row in df[df.index > entry_date].iterrows():
        low, high, close = float(row["Low"]), float(row["High"]), float(row["Close"])
        sl_hit  = low < cur_sl
        pt1_hit = stage == 0 and high > pt1
        pt2_hit = stage == 1 and high > pt2
        print(f"  {date.date()}  L={low:8.2f} H={high:8.2f} C={close:8.2f}   "
              f"SL(<{cur_sl:.2f})={sl_hit}  PT1={pt1_hit}  PT2={pt2_hit}")
        if sl_hit:
            break
        if pt1_hit:
            stage = 1
            cur_sl = entry_price
        elif pt2_hit:
            stage = 2
            cur_sl = pt1

    events = simulate_exit(shares, entry_price, entry_date, df, HOLD_END_DATE)
    print("\n  Simulated exit events:")
    for e in events:
        print(f"    {e['date'].date()}  {e['reason']:4s}  shares={e['shares']}  price={e['price']:.2f}")
    print(f"  exit_reason_summary = {classify_exit_summary(events)}")


def test_mini_scan():
    print(f"STEP 3 - mini scan: 10 stocks, {SCAN_FRIDAYS[0].date()} only, all methods/policies")
    universe = get_symbols()[:MINI_SCAN_SIZE]
    print(f"  Mini universe: {universe}")
    state = new_state()
    week_rows = run_friday_scan(SCAN_FRIDAYS[0], universe, state, verbose=True)
    print(f"\n  Week rows: {week_rows}")
    return state, week_rows


def print_checklist():
    print("=" * 70)
    print("  MULTI-SETUP BACKTEST - PRE-RUN CHECKLIST")
    print("=" * 70)
    print(f"  Scan Fridays      : {SCAN_FRIDAYS[0].date()} .. {SCAN_FRIDAYS[-1].date()}  ({len(SCAN_FRIDAYS)} weeks)")
    print(f"  Hold/exit through : {HOLD_END_DATE.date()}")
    print("  Universe          : NSE 500 (data/universe.get_symbols())")
    print(f"  Methods compared  : {', '.join(METHODS)}")
    print(f"  VCP grade filter  : only buys grades {sorted(VCP_ALLOWED_GRADES)} (C/D scanned but skipped)")
    print(f"  Re-entry policies : {', '.join(POLICIES)}")
    print(f"  Position size     : Rs.{POSITION_SIZE:,.0f} per stock (floor(size/entry_price) shares)")
    print(f"  Stop loss         : -{(1-SL_MULT)*100:.0f}% of entry (LOW-based trigger, exit at CLOSE)")
    print("                      ratchets to breakeven after PT1, to PT1 price after PT2")
    print("  Profit target 1   : +20% of entry (HIGH-based trigger) -> sell 50%")
    print("  Profit target 2   : +40% of entry (HIGH-based trigger) -> sell 50% of remainder")
    print(f"  Hard close        : {HOLD_END_DATE.date()} - any open shares closed at close, any P&L")
    print(f"  Benchmark         : Nifty 50 (^NSEI), {BENCHMARK_START.date()} -> {HOLD_END_DATE.date()}")
    print(f"  Output workbook   : {RESULTS_XLSX}")
    print(f"  Checkpoint file   : {CHECKPOINT_JSON}")
    print("=" * 70)


def run_full_backtest(resume: bool = True):
    print_checklist()
    universe = get_symbols()
    print(f"  Universe size: {len(universe)} symbols\n")

    if resume:
        completed, state, weekly_rows = load_checkpoint()
        if completed:
            print(f"  Resuming from checkpoint - already completed: "
                  f"{[d.strftime('%Y-%m-%d') for d in completed]}")
    else:
        completed, state, weekly_rows = [], new_state(), []

    for scan_date in SCAN_FRIDAYS:
        if scan_date in completed:
            print(f"  Skipping {scan_date.date()} (already in checkpoint)")
            continue
        week_rows = run_friday_scan(scan_date, universe, state)
        weekly_rows.extend(week_rows)
        completed.append(scan_date)
        save_checkpoint(completed, state, weekly_rows)

    print("\n  Computing benchmark...")
    spy_pnl_pct = compute_benchmark()

    build_excel_report(state, weekly_rows, spy_pnl_pct)
    print_terminal_summary(state, spy_pnl_pct)


# ─────────────────────────────────────────────
# ENTRY POINT
# ─────────────────────────────────────────────
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Multi-setup weekly-scan backtest engine")
    parser.add_argument("--mode", choices=["fetch_test", "exit_test", "mini_scan", "full"],
                         required=True)
    parser.add_argument("--no-resume", action="store_true",
                         help="ignore any existing checkpoint and start over")
    args = parser.parse_args()

    if args.mode == "fetch_test":
        test_fetch_single()
    elif args.mode == "exit_test":
        test_exit_single()
    elif args.mode == "mini_scan":
        print_checklist()
        test_mini_scan()
    elif args.mode == "full":
        run_full_backtest(resume=not args.no_resume)
