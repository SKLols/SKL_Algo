"""
config.py — Central configuration for the Minervini stock scanner.

All tunable constants live here. Every other module imports from this file.
When you add a new setup (Darvas, Breakout, Cup & Handle etc.), add its
class block here and import it from config in the setup's own module.

Edit freely — nothing in this file contains logic.
"""

import os

# ─────────────────────────────────────────────
# PATHS
# All output goes under the project root's /output folder.
# ─────────────────────────────────────────────
#ROOT_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
ROOT_DIR   = os.path.abspath(os.path.join(os.path.dirname(__file__)))
OUTPUT_DIR = os.path.join(ROOT_DIR, "output")
CHART_DIR  = os.path.join(OUTPUT_DIR, "charts")

# ─────────────────────────────────────────────
# UNIVERSE
# Comment/uncomment to switch between markets.
# ACTIVE_UNIVERSE is what scanner.py and market_breadth.py will use.
# ─────────────────────────────────────────────
class Universe:
    # Which universe to scan — "NSE500", "SP500", or "CUSTOM"
    ACTIVE = "NSE500"

    # NSE Nifty 500 source URL
    NSE500_URL = "https://archives.nseindia.com/content/indices/ind_nifty500list.csv"

    # S&P 500 source URL (GitHub mirror — no login required)
    SP500_URL  = "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/master/data/constituents.csv"

    # Used when ACTIVE = "CUSTOM"
    CUSTOM_SYMBOLS = [
        # "RELIANCE.NS",
        # "INFY.NS",
        # "AAPL",
        # "NVDA",
    ]

# ─────────────────────────────────────────────
# BENCHMARK
# Maps market suffix to index symbol and display name.
# Add entries here if you add new markets (e.g. LSE → "^FTSE").
# ─────────────────────────────────────────────
class Benchmark:
    SYMBOLS = {
        "NSE": "^NSEI",   # Nifty 50
        "US" : "^GSPC",   # S&P 500
    }
    NAMES = {
        "NSE": "Nifty 50",
        "US" : "S&P 500",
    }

# ─────────────────────────────────────────────
# DATA FETCHING
# Controls how far back data is downloaded for all setups.
# The extra buffer (60 days) ensures MAs are fully warmed up
# even at the start of the lookback window.
# ─────────────────────────────────────────────
class Data:
    LOOKBACK_DAYS = 600      # trading history to download (all setups share this)
    MA_WARMUP_BUFFER = 60    # extra days so 200-MA is valid at day 1 of lookback

# ─────────────────────────────────────────────
# TREND TEMPLATE  (Minervini Stage 2 filter)
# All 8 conditions must pass before any setup is evaluated.
# These thresholds are Minervini's original values — change carefully.
# ─────────────────────────────────────────────
class TrendTemplate:
    MA_PERIODS          = [50, 150, 200]   # SMAs computed for the template check
    MA200_TREND_DAYS    = 22               # "rising for 1 month" = 22 trading days
    PCT_ABOVE_52W_LOW   = 30.0             # price must be >30% above 52-week low
    PCT_BELOW_52W_HIGH  = 25.0             # price must be within 25% of 52-week high

# ─────────────────────────────────────────────
# INDICATORS  (shared across multiple setups)
# ─────────────────────────────────────────────
class Indicators:
    # EMAs added to every stock's DataFrame before setup detection
    EMA_PERIODS = [10, 20, 50, 150, 200]

    # RS rating: number of trading days used for the return comparison
    RS_LOOKBACK_DAYS = 252   # 1 trading year

    # Swing detection: bars each side required to confirm a swing H/L
    SWING_LOOKBACK = 3

# ─────────────────────────────────────────────
# VCP SETUP  (Volatility Contraction Pattern)
# ─────────────────────────────────────────────
class VCP:
    MIN_CONTRACTIONS      = 2     # need at least this many H→L swings
    MAX_CONTRACTIONS_KEPT = 6     # look back at most this many contractions
    MAX_FINAL_CONTRACTION = 10.0  # last contraction must be ≤ this % wide
    MIN_VOLUME_DRY_UP     = 0.9   # final contraction avg vol ≤ 0.9× 50-day avg
    VOLUME_VIOLATION_ALLOW= 1     # how many non-declining volume steps are OK
    NEAR_HIGH_PCT         = 5.0   # "within 5% of 52w high" bonus condition

    # Scoring weights (sum = 11 max)
    SCORE_TRIPLET_NESTED  = 4     # C3 inside C2 inside C1
    SCORE_PAIR_NESTED     = 2     # any 2-step nesting
    SCORE_TIGHT_FINAL     = 2     # final contraction ≤ MAX_FINAL_CONTRACTION
    SCORE_VOL_DRYUP       = 2     # volume dry-up confirmed
    SCORE_VOL_DECLINING   = 1     # volume declining across contractions
    SCORE_3_CONTRACTIONS  = 1     # at least 3 contractions found
    SCORE_NEAR_HIGH       = 1     # price within NEAR_HIGH_PCT of 52w high

# ─────────────────────────────────────────────
# BREAKOUT SETUP  (add parameters when you build this)
# ─────────────────────────────────────────────
class Breakout:
    # Volume surge: breakout day volume must be ≥ this × 50-day avg
    MIN_VOLUME_SURGE        = 1.5
    # Max % below 52-week high to qualify as a valid breakout zone
    MAX_PCT_BELOW_HIGH      = 3.0
    # Price must be > this % above 52w low
    MIN_RISE_FROM_LOW_PCT   = 30.0
    # 1-week return must exceed this % (momentum confirmation)
    MIN_1W_RETURN_PCT       = 3.0
    # Minimum daily volume
    MIN_VOLUME              = 100_000
    # Short-range base parameters (trading days)
    SHORT_BASE_MIN_DAYS     = 10
    SHORT_BASE_MAX_DAYS     = 20
    MAX_BASE_RANGE_PCT      = 8.0    # tight range inside the short base
    # Long-range base parameters (weeks)
    LONG_BASE_MIN_WEEKS     = 6
    LONG_BASE_MAX_WEEKS     = 52
    LONG_BASE_RANGE_PCT     = 25.0   # allowed range inside the long base
    # Fundamental thresholds
    MIN_PROFIT_GROWTH_PCT   = 15.0
    MIN_SALES_GROWTH_PCT    = 10.0
    MIN_MARKET_CAP          = 200    # Cr or $M

# ─────────────────────────────────────────────
# DARVAS BOX SETUP  (add parameters when you build this)
# ─────────────────────────────────────────────
class Darvas:
    # Weeks to look back when defining the Darvas box top
    BOX_LOOKBACK_WEEKS    = 52
    # Box ceiling tolerance: high can exceed prev box top by this %
    BOX_TOLERANCE_PCT     = 1.5
    # Minimum number of weeks price must stay inside the box
    MIN_BOX_WEEKS         = 3
    # Volume must drop ≥ this % inside the box vs. the breakout bar
    MIN_VOLUME_DECLINE_PCT = 20.0
    # Maximum box range (high to low) as % of box top — tighter = better
    MAX_BOX_RANGE_PCT     = 15.0
    # Price must be within this % of 52w high
    MAX_PCT_BELOW_HIGH    = 10.0
    # Price must have risen this % above its 52w low (strong prior move)
    MIN_RISE_FROM_LOW_PCT = 100.0
    # Minimum and maximum price filter
    MIN_PRICE             = 10.0
    MAX_PRICE             = 1000.0
    # Minimum daily volume
    MIN_VOLUME            = 100_000

# ─────────────────────────────────────────────
# POWERPLAY SETUP  (add parameters when you build this)
# ─────────────────────────────────────────────
class PowerPlay:
    # Single-day gain that qualifies as a "power day"
    MIN_SINGLE_DAY_GAIN_PCT = 0.75
    # Volume on the power day must be ≥ this × 50-day avg
    MIN_POWER_DAY_VOLUME    = 1.25
    # How many recent sessions to scan for power days
    LOOKBACK_DAYS           = 20
    # 1-year return must exceed this % (strong prior uptrend)
    MIN_1Y_RETURN_PCT       = 100.0
    # Price must be within this range below 52w high (1–10%)
    MIN_PCT_BELOW_HIGH      = 1.0
    MAX_PCT_BELOW_HIGH      = 10.0
    # Price must be > this % above 52w low
    MIN_RISE_FROM_LOW_PCT   = 100.0
    # 10-day price range must be ≤ this % (coiling / tightening)
    MAX_10D_RANGE_PCT       = 5.0
    # Minimum daily volume
    MIN_VOLUME              = 100_000
    # Fundamental thresholds (used when _get_fundamentals is enabled)
    MIN_PROFIT_GROWTH_PCT   = 25.0   # YoY quarterly EPS growth %
    MIN_SALES_GROWTH_PCT    = 20.0   # YoY quarterly revenue growth %
    MIN_ROE_PCT             = 15.0   # Return on equity %
    MAX_DEBT_EQUITY         = 1.0    # Debt-to-equity ratio
    MIN_MARKET_CAP          = 500    # Cr (NSE) or $M (US)

# ─────────────────────────────────────────────
# CUP & HANDLE SETUP  (add parameters when you build this)
# ─────────────────────────────────────────────
class CupHandle:
    # Cup depth: how far price falls from left rim to base (%)
    MIN_CUP_DEPTH_PCT       = 10.0
    MAX_CUP_DEPTH_PCT       = 35.0
    # Cup duration in trading weeks
    MIN_CUP_WEEKS           = 7
    MAX_CUP_WEEKS           = 65
    # Handle: must retrace ≤ this % of the cup depth
    MAX_HANDLE_RETRACE_PCT  = 50.0
    # Handle duration in trading days
    MIN_HANDLE_DAYS         = 5
    MAX_HANDLE_DAYS         = 15
    # Handle must form in the upper half of the cup
    HANDLE_UPPER_HALF       = True
    # Price range vs 52w high
    MIN_PCT_BELOW_HIGH      = 2.0
    MAX_PCT_BELOW_HIGH      = 10.0
    # Price must be > this % above 52w low
    MIN_RISE_FROM_LOW_PCT   = 50.0
    # Return thresholds
    MIN_6M_RETURN_PCT       = 10.0
    MIN_1Y_RETURN_PCT       = 20.0
    # Minimum daily volume
    MIN_VOLUME              = 50_000
    # Fundamental thresholds
    MIN_PROFIT_GROWTH_PCT   = 20.0
    MIN_SALES_GROWTH_PCT    = 15.0
    MAX_DEBT_EQUITY         = 1.5
    MIN_MARKET_CAP          = 500    # Cr or $M

# ─────────────────────────────────────────────
# MARKET BREADTH
# Used by market_breadth.py (standalone entry point).
# ─────────────────────────────────────────────
class MarketBreadth:
    # If this many stocks pass the trend template → market is healthy
    BULL_THRESHOLD          = 200
    # Percentage equivalent (whichever is hit first)
    BULL_THRESHOLD_PCT      = 60.0   # 60% of universe passing = healthy
    # Label thresholds for the three-tier display
    LABEL_BULL              = "HEALTHY — setups are high-probability"
    LABEL_NEUTRAL           = "MIXED — be selective"
    LABEL_BEAR              = "CAUTION — wait for better conditions"

# ─────────────────────────────────────────────
# CHART OUTPUT
# Controls the appearance and save behaviour of all charts.
# ─────────────────────────────────────────────
class Chart:
    # How many calendar days of OHLCV to show (not the full history)
    LOOKBACK_DAYS           = 180

    # Save charts for all VCP grades (A/B/C/D).
    # Set to False to save Grade A only.
    SAVE_ALL_GRADES         = True

    # Chart resolution (higher = sharper, slower)
    DPI                     = 130

    # Figure dimensions (width × height in inches)
    FIGSIZE                 = (16, 9)

    # Price panel vs volume panel height ratio
    PANEL_RATIOS            = (3, 1)

    # Dark-theme background colour
    BACKGROUND              = "#0d0d0d"
    GRID_COLOR              = "#1c1c1c"

    # EMA line colours and widths  {column_name: (hex_color, line_width)}
    EMA_STYLE = {
        "EMA_10" : ("#e65100", 0.9),
        "EMA_20" : ("#0277bd", 0.9),
        "EMA_50" : ("#1b5e20", 1.2),
        "EMA_150": ("#4a148c", 1.2),
        "EMA_200": ("#b71c1c", 1.4),
    }

    # Candlestick colours
    CANDLE_UP   = "#26a69a"
    CANDLE_DOWN = "#ef5350"
    WICK_UP     = "#80cbc4"
    WICK_DOWN   = "#ef9a9a"

    # Contraction band colours (cycled C1, C2, C3 …)
    BAND_COLORS = ["#ffeb3b", "#ff9800", "#f44336", "#ce93d8", "#80cbc4", "#a5d6a7"]

    # Pivot line
    PIVOT_COLOR = "#ffeb3b"

    # Grade badge colours
    GRADE_COLORS = {
        "A": "#00c853",
        "B": "#2979ff",
        "C": "#ff6d00",
        "D": "#aa00ff",
    }

    # Swing marker colours
    SWING_HIGH_COLOR = "#f44336"   # ▼ above candle
    SWING_LOW_COLOR  = "#4caf50"   # ▲ below candle
    SWING_MARKER_SIZE= 55

# ─────────────────────────────────────────────
# EXCEL EXPORT
# ─────────────────────────────────────────────
class Export:
    VCP_FILENAME        = "vcp_scan_results.xlsx"
    BREADTH_FILENAME    = "market_breadth.xlsx"
    SHEET_VCP           = "VCP_Setups"
    SHEET_BREADTH       = "Breadth"
