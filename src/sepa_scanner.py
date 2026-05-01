import time
import math
import requests
import pandas as pd
import yfinance as yf
from datetime import datetime

# ============================================================
# CONFIG
# ============================================================

# ALPHA_VANTAGE_API_KEY = "YOUR_API_KEY"
# ALPHA_VANTAGE_API_KEY = "RZMVY9EYMAT8LIF7"
ALPHA_VANTAGE_API_KEY = "X6G40X7M8G4L7EIX"


STOCKS = [
    "TPR",
    "ALB",
    "STLD",
    "TRGP",
    "WAB",
    "EME",
    "STT",
    "NTRS",
    "KLAC",
    "HLT",
    "BK", 
    "CAT",
    "RL",
    "MAR"

    # "BK", "CAT", "FIX", "HLT", "HUBB", "KEYS", "KLAC", "MAR", "NTRS", "STT",
    # "TER", "EME", "WAB", "AMAT", "FCX", "JCI", "ON", "PCAR", "RL", "JBHT",
    # "TJX", "WELL", "ODFL", "SATS", "TRGP", "STLD", "CFG", "ALB", "KEY", "DOV",
    # "TPR", "PNC", "GS", "DE", "FITB", "CTRA", "SCHW", "MLM"
]

OUTPUT_EXCEL = "us_quarterly_rs_eps_sales.xlsx"

# Alpha Vantage free tier is limited, so keep this conservative.
SLEEP_SECONDS = 12.5


# ============================================================
# HELPERS
# ============================================================

def alpha_vantage_get(function_name: str, symbol: str, apikey: str) -> dict:
    """
    Fetch JSON from Alpha Vantage.
    """
    url = "https://www.alphavantage.co/query"
    params = {
        "function": function_name,
        "symbol": symbol,
        "apikey": apikey
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    data = resp.json()

    if "Error Message" in data:
        raise ValueError(f"{symbol}: Alpha Vantage error: {data['Error Message']}")
    if "Information" in data:
        raise ValueError(f"{symbol}: Alpha Vantage info: {data['Information']}")
    return data


def safe_float(x):
    try:
        if x is None or x == "" or str(x).lower() == "none":
            return None
        return float(x)
    except Exception:
        return None


def format_quarter_label(fiscal_date_ending: str) -> str:
    """
    Convert '2025-12-31' -> 'Dec-25'
    """
    dt = datetime.strptime(fiscal_date_ending, "%Y-%m-%d")
    return dt.strftime("%b-%y")


def pct_change_yoy(current, previous):
    if current is None or previous in (None, 0):
        return None
    return (current - previous) / abs(previous) * 100.0


def format_pct(p):
    if p is None or (isinstance(p, float) and math.isnan(p)):
        return ""
    sign = "+" if p >= 0 else ""
    return f"{sign}{p:.0f}%"


def format_number(x, decimals=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return ""
    return f"{x:.{decimals}f}"


def format_sales_cr(revenue_usd):
    """
    Convert USD revenue to "crore-style" number only for display similarity.
    1 crore = 10,000,000
    For US stocks this is just a presentation format, not INR conversion.
    """
    if revenue_usd is None:
        return None
    return revenue_usd / 1e7


# ============================================================
# RS RATING PROXY
# ============================================================

def get_12m_return(symbol: str):
    """
    12-month price return using Yahoo Finance.
    Handles newer yfinance MultiIndex output safely.
    """
    try:
        df = yf.download(
            symbol,
            period="14mo",
            interval="1d",
            auto_adjust=True,
            progress=False,
            threads=False
        )

        if df is None or df.empty:
            print(f"RS error for {symbol}: empty download")
            return None

        # New yfinance can return MultiIndex columns like:
        # MultiIndex([('Close','AMAT'), ('High','AMAT'), ...], names=['Price','Ticker'])
        if isinstance(df.columns, pd.MultiIndex):
            # Keep only first level: Close, High, Low, Open, Volume
            df.columns = df.columns.get_level_values(0)

        if "Close" not in df.columns:
            print(f"RS error for {symbol}: Close column missing")
            return None

        close = pd.to_numeric(df["Close"], errors="coerce").dropna()

        if len(close) < 220:
            print(f"RS error for {symbol}: not enough valid closes ({len(close)})")
            return None

        start_price = float(close.iloc[0])
        end_price = float(close.iloc[-1])

        if start_price <= 0:
            print(f"RS error for {symbol}: invalid start price {start_price}")
            return None

        return (end_price / start_price - 1.0) * 100.0

    except Exception as e:
        print(f"RS error for {symbol}: {e}")
        return None


def compute_rs_ratings(symbols: list[str]) -> pd.DataFrame:
    rows = []
    for sym in symbols:
        ret_12m = get_12m_return(sym)
        rows.append({
            "Symbol": sym,
            "Return_12M_pct": ret_12m
        })

    df = pd.DataFrame(rows)

    valid = df["Return_12M_pct"].dropna()
    if valid.empty:
        df["RS_Rating"] = None
        return df

    df["Percentile"] = df["Return_12M_pct"].rank(pct=True, method="average")
    df["RS_Rating"] = df["Percentile"].apply(
        lambda x: int(round(1 + x * 98)) if pd.notna(x) else None
    )

    return df[["Symbol", "Return_12M_pct", "RS_Rating"]]


# ============================================================
# FUNDAMENTALS
# ============================================================

def fetch_quarterly_eps_and_revenue(symbol: str, apikey: str) -> pd.DataFrame:
    """
    Merge Alpha Vantage EARNINGS + INCOME_STATEMENT quarterly data.

    Returns columns:
    - fiscalDateEnding
    - quarter_label
    - reportedEPS
    - revenue
    - eps_yoy_pct
    - revenue_yoy_pct
    """
    earnings = alpha_vantage_get("EARNINGS", symbol, apikey)
    income = alpha_vantage_get("INCOME_STATEMENT", symbol, apikey)

    q_eps = earnings.get("quarterlyEarnings", [])
    q_income = income.get("quarterlyReports", [])

    if not q_eps or not q_income:
        return pd.DataFrame()

    eps_df = pd.DataFrame(q_eps)
    inc_df = pd.DataFrame(q_income)

    if "fiscalDateEnding" not in eps_df.columns or "fiscalDateEnding" not in inc_df.columns:
        return pd.DataFrame()

    eps_df = eps_df[["fiscalDateEnding", "reportedEPS"]].copy()
    inc_df = inc_df[["fiscalDateEnding", "totalRevenue"]].copy()

    eps_df["reportedEPS"] = eps_df["reportedEPS"].apply(safe_float)
    inc_df["totalRevenue"] = inc_df["totalRevenue"].apply(safe_float)

    merged = pd.merge(eps_df, inc_df, on="fiscalDateEnding", how="outer")
    merged = merged.sort_values("fiscalDateEnding", ascending=False).reset_index(drop=True)

    # Keep a bit more than 8 so YoY matching is easy
    merged = merged.head(12).copy()
    merged["quarter_label"] = merged["fiscalDateEnding"].apply(format_quarter_label)

    # Build YoY map by exact quarter label one year back
    # Example: Dec-25 compares to Dec-24
    merged["year"] = merged["fiscalDateEnding"].str[:4].astype(int)
    merged["month_day"] = merged["fiscalDateEnding"].str[5:]

    # For each row, find same fiscal quarter previous year
    yoy_eps = []
    yoy_rev = []

    for _, row in merged.iterrows():
        prev_year = row["year"] - 1
        prev_match = merged[
            (merged["year"] == prev_year) &
            (merged["month_day"] == row["month_day"])
        ]

        if prev_match.empty:
            yoy_eps.append(None)
            yoy_rev.append(None)
        else:
            prev_eps = safe_float(prev_match.iloc[0]["reportedEPS"])
            prev_rev = safe_float(prev_match.iloc[0]["totalRevenue"])

            yoy_eps.append(pct_change_yoy(row["reportedEPS"], prev_eps))
            yoy_rev.append(pct_change_yoy(row["totalRevenue"], prev_rev))

    merged["eps_yoy_pct"] = yoy_eps
    merged["revenue_yoy_pct"] = yoy_rev

    # Keep latest 8 quarters for output
    merged = merged.head(8).copy()
    merged.rename(columns={"reportedEPS": "EPS", "totalRevenue": "Revenue"}, inplace=True)

    return merged[[
        "fiscalDateEnding",
        "quarter_label",
        "EPS",
        "eps_yoy_pct",
        "Revenue",
        "revenue_yoy_pct"
    ]]


def make_display_table(symbol: str, rs_rating, ret_12m, qdf: pd.DataFrame) -> pd.DataFrame:
    """
    Build final table in the format the user requested.
    """
    if qdf.empty:
        return pd.DataFrame()

    out = pd.DataFrame({
        "Date(Quarter)": qdf["quarter_label"],
        "EPS": qdf["EPS"].apply(lambda x: format_number(x, 2)),
        "%Chg_EPS": qdf["eps_yoy_pct"].apply(format_pct),
        "Sales(Cr)": qdf["Revenue"].apply(lambda x: format_number(format_sales_cr(x), 1) if x is not None else ""),
        "%Chg_Sales": qdf["revenue_yoy_pct"].apply(format_pct),
    })

    # Add metadata columns at front
    out.insert(0, "RS_Rating", rs_rating if rs_rating is not None else "")
    out.insert(1, "Return_12M_pct", f"{ret_12m:.1f}%" if ret_12m is not None else "")
    out.insert(0, "Symbol", symbol)

    return out


# ============================================================
# MAIN
# ============================================================

def main():
    if not ALPHA_VANTAGE_API_KEY or ALPHA_VANTAGE_API_KEY == "YOUR_API_KEY":
        raise ValueError("Please set ALPHA_VANTAGE_API_KEY first.")

    print("Computing RS rating proxy from 12-month returns...")
    rs_df = compute_rs_ratings(STOCKS)
    rs_map = rs_df.set_index("Symbol").to_dict("index")

    all_tables = []
    summary_rows = []

    with pd.ExcelWriter(OUTPUT_EXCEL, engine="openpyxl") as writer:
        # Summary sheet first
        rs_df_sorted = rs_df.sort_values(["RS_Rating", "Return_12M_pct"], ascending=[False, False])
        rs_df_sorted.to_excel(writer, sheet_name="RS_Summary", index=False)

        for i, symbol in enumerate(STOCKS, start=1):
            print(f"[{i}/{len(STOCKS)}] {symbol}")

            rs_info = rs_map.get(symbol, {})
            rs_rating = rs_info.get("RS_Rating")
            ret_12m = rs_info.get("Return_12M_pct")

            try:
                qdf = fetch_quarterly_eps_and_revenue(symbol, ALPHA_VANTAGE_API_KEY)
                table = make_display_table(symbol, rs_rating, ret_12m, qdf)

                if table.empty:
                    summary_rows.append({
                        "Symbol": symbol,
                        "RS_Rating": rs_rating,
                        "Return_12M_pct": ret_12m,
                        "Status": "No quarterly data"
                    })
                else:
                    sheet_name = symbol[:31]
                    table.to_excel(writer, sheet_name=sheet_name, index=False)
                    all_tables.append(table)

                    latest = qdf.iloc[0]
                    summary_rows.append({
                        "Symbol": symbol,
                        "RS_Rating": rs_rating,
                        "Return_12M_pct": ret_12m,
                        "Latest_Quarter": latest["quarter_label"],
                        "Latest_EPS": latest["EPS"],
                        "Latest_EPS_YoY_pct": latest["eps_yoy_pct"],
                        "Latest_Revenue": latest["Revenue"],
                        "Latest_Revenue_YoY_pct": latest["revenue_yoy_pct"],
                        "Status": "OK"
                    })

            except Exception as e:
                summary_rows.append({
                    "Symbol": symbol,
                    "RS_Rating": rs_rating,
                    "Return_12M_pct": ret_12m,
                    "Status": f"ERROR: {e}"
                })

            # Alpha Vantage free tier pacing
            if i < len(STOCKS):
                time.sleep(SLEEP_SECONDS)

        summary_df = pd.DataFrame(summary_rows)
        summary_df = summary_df.sort_values(["RS_Rating", "Return_12M_pct"], ascending=[False, False])
        summary_df.to_excel(writer, sheet_name="Summary", index=False)

    print(f"\nSaved to: {OUTPUT_EXCEL}")

    # Also print a compact view in console
    print("\nTop RS names:")
    print(rs_df.sort_values(["RS_Rating", "Return_12M_pct"], ascending=[False, False]).head(15).to_string(index=False))

    # Example printout per symbol
    for symbol in STOCKS[:5]:
        try:
            qdf = fetch_quarterly_eps_and_revenue(symbol, ALPHA_VANTAGE_API_KEY)
            rs_info = rs_map.get(symbol, {})
            table = make_display_table(symbol, rs_info.get("RS_Rating"), rs_info.get("Return_12M_pct"), qdf)
            if not table.empty:
                print(f"\nQuarterly Earnings ({symbol})")
                print(table.to_string(index=False))
        except Exception:
            pass

test = yf.download("AMAT", period="14mo", interval="1d", auto_adjust=True, progress=False)
print(type(test.columns))
print(test.columns)
print(test.head())

if __name__ == "__main__":
    main()