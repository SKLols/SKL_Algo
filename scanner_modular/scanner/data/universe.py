"""
data/universe.py — Stock universe loaders.

Returns a list of ticker symbols ready for yfinance.
Switch active universe from config.py (Universe.ACTIVE).
"""
import pandas as pd
from config import Universe


def get_nse500_symbols() -> list[str]:
    """Download and return Nifty 500 symbols in yfinance format (e.g. RELIANCE.NS)."""
    df = pd.read_csv(Universe.NSE500_URL)
    return [s + ".NS" for s in df["Symbol"].tolist()]


def get_sp500_symbols() -> list[str]:
    """Download and return S&P 500 symbols in yfinance format (e.g. BRK-B)."""
    df = pd.read_csv(Universe.SP500_URL)
    return [s.replace(".", "-") for s in df["Symbol"].tolist()]


def get_symbols() -> list[str]:
    """
    Return the active universe based on Universe.ACTIVE in config.py.
    Call this from scanner.py and market_breadth.py — never hardcode a list there.
    """
    if Universe.ACTIVE == "NSE500":
        return get_nse500_symbols()
    elif Universe.ACTIVE == "SP500":
        return get_sp500_symbols()
    elif Universe.ACTIVE == "CUSTOM":
        if not Universe.CUSTOM_SYMBOLS:
            raise ValueError("Universe.ACTIVE is 'CUSTOM' but CUSTOM_SYMBOLS list is empty in config.py")
        return Universe.CUSTOM_SYMBOLS
    else:
        raise ValueError(f"Unknown Universe.ACTIVE value: '{Universe.ACTIVE}'. "
                         f"Use 'NSE500', 'SP500', or 'CUSTOM'.")
