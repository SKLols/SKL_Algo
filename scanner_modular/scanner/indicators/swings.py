"""
indicators/swings.py — Swing high / low detection.

Uses CLOSING PRICES only (not intraday highs/lows) to locate pivot points.
Both VCP and future setups (Cup & Handle, Darvas) import from here.
"""
import pandas as pd

from config import Indicators


def find_swing_highs(close: pd.Series, n: int | None = None) -> pd.Series:
    """
    Return a boolean Series — True where close[i] is a swing high.

    A bar is a swing high when its close is strictly greater than
    every close in the n bars to the left AND the n bars to the right.

    Args:
        close: Closing price Series.
        n:     Number of bars each side required (defaults to Indicators.SWING_LOOKBACK).
    """
    if n is None:
        n = Indicators.SWING_LOOKBACK

    highs = pd.Series(False, index=close.index)
    arr   = close.values
    for i in range(n, len(arr) - n):
        if arr[i] > arr[i - n:i].max() and arr[i] > arr[i + 1:i + n + 1].max():
            highs.iloc[i] = True
    return highs


def find_swing_lows(close: pd.Series, n: int | None = None) -> pd.Series:
    """
    Return a boolean Series — True where close[i] is a swing low.

    A bar is a swing low when its close is strictly less than
    every close in the n bars to the left AND the n bars to the right.

    Args:
        close: Closing price Series.
        n:     Number of bars each side required (defaults to Indicators.SWING_LOOKBACK).
    """
    if n is None:
        n = Indicators.SWING_LOOKBACK

    lows = pd.Series(False, index=close.index)
    arr  = close.values
    for i in range(n, len(arr) - n):
        if arr[i] < arr[i - n:i].min() and arr[i] < arr[i + 1:i + n + 1].min():
            lows.iloc[i] = True
    return lows


def build_alternating_swings(close: pd.Series, n: int | None = None) -> list[tuple]:
    """
    Build a cleaned, alternating H/L swing sequence from a Close price Series.

    Steps:
      1. Detect all swing highs and lows independently.
      2. Merge into a time-ordered list.
      3. Remove consecutive same-type swings — for highs keep the highest close,
         for lows keep the lowest close.

    Returns:
        List of (price: float, type: str, date: pd.Timestamp) tuples,
        alternating H and L, oldest first.
    """
    if n is None:
        n = Indicators.SWING_LOOKBACK

    sh_mask = find_swing_highs(close, n=n)
    sl_mask = find_swing_lows(close,  n=n)

    sh = pd.DataFrame({"price": close[sh_mask], "type": "H"})
    sl = pd.DataFrame({"price": close[sl_mask], "type": "L"})
    swings = pd.concat([sh, sl]).sort_index()

    cleaned: list[tuple] = []
    for _, row in swings.iterrows():
        if cleaned and cleaned[-1][1] == row["type"]:
            # Same type as the last swing — keep only the more extreme close
            if row["type"] == "H" and row["price"] > cleaned[-1][0]:
                cleaned[-1] = (row["price"], row["type"], row.name)
            elif row["type"] == "L" and row["price"] < cleaned[-1][0]:
                cleaned[-1] = (row["price"], row["type"], row.name)
        else:
            cleaned.append((row["price"], row["type"], row.name))

    return cleaned
