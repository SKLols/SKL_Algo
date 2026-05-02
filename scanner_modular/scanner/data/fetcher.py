"""
data/fetcher.py — Data download and RS computation.

Responsibilities:
  - Download OHLCV data for a stock via yfinance
  - Cache benchmark index data (one download shared across all stocks)
  - Compute Relative Strength (RS) vs the correct benchmark
  - Add EMA columns to the DataFrame

All other modules receive a clean DataFrame from here — they never call yfinance directly.
"""
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from config import Data, Benchmark, Indicators

# Module-level cache: benchmark data is downloaded once and reused for every stock
_BENCHMARK_CACHE: dict = {}


# ─────────────────────────────────────────────
# BENCHMARK HELPERS
# ─────────────────────────────────────────────

def get_benchmark_symbol(symbol: str) -> str:
    """Return the index ticker for the market this stock belongs to."""
    key = "NSE" if symbol.endswith(".NS") else "US"
    return Benchmark.SYMBOLS[key]


def get_benchmark_name(symbol: str) -> str:
    """Return the human-readable benchmark name (e.g. 'Nifty 50')."""
    key = "NSE" if symbol.endswith(".NS") else "US"
    return Benchmark.NAMES[key]


def get_benchmark_data(symbol: str, start, end) -> pd.DataFrame:
    """
    Download benchmark OHLCV. Results are cached by (symbol, start, end)
    so the same index is only downloaded once per scanner run.
    """
    cache_key = (symbol, str(start), str(end))
    if cache_key in _BENCHMARK_CACHE:
        return _BENCHMARK_CACHE[cache_key]
    df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    _BENCHMARK_CACHE[cache_key] = df
    return df


# ─────────────────────────────────────────────
# RS COMPUTATION
# ─────────────────────────────────────────────

def _extract_close(series_or_df) -> pd.Series | None:
    """Safely extract a Close price Series from either a Series or DataFrame."""
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


def compute_rs(symbol: str, df: pd.DataFrame, benchmark_df: pd.DataFrame) -> float | None:
    """
    Compute Relative Strength of symbol vs benchmark over RS_LOOKBACK_DAYS.
    Returns the percentage outperformance (positive = stronger than index).
    Returns None if data is insufficient.
    """
    if df.empty or benchmark_df.empty:
        return None

    # Validate Close column exists
    has_close = lambda d: "Close" in d.columns or (
        isinstance(d.columns, pd.MultiIndex) and
        any(col[-1] == "Close" for col in d.columns)
    )
    if not has_close(df) or not has_close(benchmark_df):
        return None

    symbol_close    = _extract_close(df)
    benchmark_close = _extract_close(benchmark_df)
    if symbol_close is None or benchmark_close is None:
        return None

    lookback = Indicators.RS_LOOKBACK_DAYS
    symbol_start = float(symbol_close.iloc[-lookback]) if len(symbol_close) >= lookback else float(symbol_close.iloc[0])
    bench_start  = float(benchmark_close.iloc[-lookback]) if len(benchmark_close) >= lookback else float(benchmark_close.iloc[0])

    if symbol_start <= 0 or bench_start <= 0:
        return None

    symbol_return    = float(symbol_close.iloc[-1]) / symbol_start - 1
    benchmark_return = float(benchmark_close.iloc[-1]) / bench_start - 1
    return round(100 * (symbol_return - benchmark_return), 2)


# ─────────────────────────────────────────────
# STOCK DATA DOWNLOAD
# ─────────────────────────────────────────────

def add_ema_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Add EMA columns defined in Indicators.EMA_PERIODS to the DataFrame in-place."""
    for period in Indicators.EMA_PERIODS:
        df[f"EMA_{period}"] = df["Close"].ewm(span=period, adjust=False).mean()
    return df


def fetch_stock(symbol: str) -> dict:
    """
    Download and clean OHLCV data for one stock.

    Returns a dict with keys:
      "df"    — cleaned DataFrame with EMA columns added (or None on failure)
      "error" — error string (or None on success)
      "start" — start date used for the download
      "end"   — end date used for the download
    """
    end   = datetime.today()
    start = end - timedelta(days=Data.LOOKBACK_DAYS + Data.MA_WARMUP_BUFFER)

    try:
        df = yf.download(symbol, start=start, end=end, progress=False, auto_adjust=True)
    except Exception as e:
        return {"df": None, "error": str(e), "start": start, "end": end}

    if df.empty or len(df) < 60:
        return {"df": None, "error": "Insufficient data", "start": start, "end": end}

    # Flatten MultiIndex columns (yfinance sometimes returns them)
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    df = df.dropna(subset=["Close"])
    df = df[df["Close"] > 0]

    if df.empty or len(df) < 60:
        return {"df": None, "error": "Insufficient data after cleaning", "start": start, "end": end}

    df = add_ema_columns(df)
    return {"df": df, "error": None, "start": start, "end": end}
