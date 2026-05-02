"""
indicators/trend_template.py — Minervini Stage 2 Trend Template.

Checks all 8 conditions. Every setup module gates on trend["all_pass"]
before running its own detection logic. Run this standalone via
market_breadth.py to assess overall market health.
"""
import numpy as np
import pandas as pd

from config import TrendTemplate


def check_trend_template(df: pd.DataFrame) -> dict:
    """
    Evaluate all 8 Minervini Trend Template conditions against a stock DataFrame.

    Returns a dict containing:
      - one bool per condition (True = passes)
      - "all_pass": True only if every condition is True
      - "ma50", "ma150", "ma200": current MA values (rounded)
      - "pct_above_52w_low": how far price is above the 52-week low (%)
      - "pct_below_52w_high": how far price is below the 52-week high (%)
    """
    close   = df["Close"]
    current = float(close.iloc[-1])

    ma50  = float(close.rolling(50).mean().iloc[-1])
    ma150 = float(close.rolling(150).mean().iloc[-1])
    ma200 = float(close.rolling(200).mean().iloc[-1])

    # MA200 trend: is it higher than it was TrendTemplate.MA200_TREND_DAYS ago?
    trend_days = TrendTemplate.MA200_TREND_DAYS
    if len(close) > 200 + trend_days:
        ma200_prev   = float(close.rolling(200).mean().iloc[-trend_days])
        ma200_rising = ma200 > ma200_prev
    else:
        ma200_rising = False

    high_52w = float(close.tail(252).max())
    low_52w  = float(close.tail(252).min())

    pct_above_low  = 100.0 * (current - low_52w)  / low_52w  if low_52w  > 0 else 0.0
    pct_below_high = 100.0 * (high_52w - current) / high_52w if high_52w > 0 else 100.0

    conditions = {
        "price_above_ma50"      : current > ma50,
        "price_above_ma150"     : current > ma150,
        "price_above_ma200"     : current > ma200,
        "ma50_gt_ma150"         : ma50  > ma150,
        "ma150_gt_ma200"        : ma150 > ma200,
        "ma200_rising"          : ma200_rising,
        "above_52w_low_30pct"   : pct_above_low  > TrendTemplate.PCT_ABOVE_52W_LOW,
        "within_52w_high_25pct" : pct_below_high < TrendTemplate.PCT_BELOW_52W_HIGH,
    }

    conditions["all_pass"]           = all(conditions.values())
    conditions["ma50"]               = round(ma50,  2)
    conditions["ma150"]              = round(ma150, 2)
    conditions["ma200"]              = round(ma200, 2)
    conditions["pct_above_52w_low"]  = round(pct_above_low,  1)
    conditions["pct_below_52w_high"] = round(pct_below_high, 1)

    return conditions
