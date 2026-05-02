"""
output/charts.py — Chart generation for all setups.

Produces dark-theme candlestick charts annotated with:
  • EMA 10 / 20 / 50 / 150 / 200
  • Swing high (▼) and swing low (▲) markers
  • Shaded contraction bands with % labels
  • Pivot breakout line + "buy above" label
  • Volume panel with dry-up highlight
  • Grade badge and VCP score
  • Trend template summary footer

Uses Agg backend (no GUI, safe for threaded/server use).
"""
import matplotlib
matplotlib.use("Agg")

import os
import numpy as np
import pandas as pd
import mplfinance as mpf
import matplotlib.pyplot as plt
import matplotlib.lines as mlines

from config import Chart, Benchmark

os.makedirs(Chart.__dict__.get("CHART_DIR", ""), exist_ok=True)  # guard


# ─────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────

def _grade_from_quality(vcp_quality: str) -> str:
    """Extract single-letter grade (A/B/C/D/Fail) from the quality string."""
    q = vcp_quality or ""
    for g in ("A", "B", "C", "D"):
        if q.startswith(g):
            return g
    return "Fail"


def _benchmark_name(symbol: str) -> str:
    key = "NSE" if symbol.endswith(".NS") else "US"
    return Benchmark.NAMES[key]


# ─────────────────────────────────────────────
# MAIN CHART FUNCTION
# ─────────────────────────────────────────────

def plot_vcp_chart(symbol: str,
                   df_full: pd.DataFrame,
                   vcp: dict,
                   trend: dict,
                   rs_value,
                   save_path: str) -> str:
    """
    Render and save a VCP chart for one stock.

    Args:
        symbol:    Ticker (e.g. "RELIANCE.NS" or "NVDA").
        df_full:   Full OHLCV + EMA DataFrame from fetcher.
        vcp:       Result dict from detect_vcp().
        trend:     Result dict from check_trend_template().
        rs_value:  Float RS % vs benchmark, or None.
        save_path: Absolute path where the PNG will be saved.

    Returns:
        save_path on success.
    """
    grade        = _grade_from_quality(vcp.get("vcp_quality", ""))
    grade_color  = Chart.GRADE_COLORS.get(grade, "#9e9e9e")
    contractions = vcp.get("contractions", [])
    cleaned      = vcp.get("cleaned_swings", [])
    pivot        = vcp.get("pivot_price")
    vol_dry_up   = vcp.get("volume_dry_up", False)
    vol_ratio    = vcp.get("vol_ratio_final")

    # ── Trim to chart window ──
    chart_start = df_full.index[-1] - pd.Timedelta(days=Chart.LOOKBACK_DAYS)
    df = df_full[df_full.index >= chart_start].copy()
    if len(df) < 20:
        df = df_full.tail(60).copy()

    currency = "₹" if symbol.endswith(".NS") else "$"
    n = len(df)

    # ── EMA addplots ──
    ema_addplots       = []
    ema_legend_handles = []
    for col, (color, lw) in Chart.EMA_STYLE.items():
        series = df_full[col].reindex(df.index) if col in df_full.columns \
                 else df["Close"].ewm(span=int(col.split("_")[1]), adjust=False).mean()
        ema_addplots.append(
            mpf.make_addplot(series, panel=0, color=color, width=lw, alpha=0.85))
        ema_legend_handles.append(
            mlines.Line2D([], [], color=color, linewidth=lw,
                          label=col.replace("_", " ")))

    # ── Swing markers ──
    sh_marker = pd.Series(np.nan, index=df.index)
    sl_marker = pd.Series(np.nan, index=df.index)
    for price, stype, date in cleaned:
        if date in df.index:
            if stype == "H":
                sh_marker[date] = df.loc[date, "High"] * 1.006
            else:
                sl_marker[date] = df.loc[date, "Low"]  * 0.994

    marker_plots = []
    if sh_marker.notna().any():
        marker_plots.append(mpf.make_addplot(
            sh_marker, type="scatter",
            markersize=Chart.SWING_MARKER_SIZE,
            marker="v", color=Chart.SWING_HIGH_COLOR, panel=0))
    if sl_marker.notna().any():
        marker_plots.append(mpf.make_addplot(
            sl_marker, type="scatter",
            markersize=Chart.SWING_MARKER_SIZE,
            marker="^", color=Chart.SWING_LOW_COLOR, panel=0))

    # ── Volume colours: highlight final contraction window ──
    vol_colors  = []
    final_start = contractions[-1]["high_date"] if contractions else df.index[-20]
    for i, idx in enumerate(df.index):
        up       = df["Close"].iloc[i] >= df["Close"].iloc[i - 1] if i > 0 else True
        in_final = (idx >= final_start) and vol_dry_up
        if in_final:
            vol_colors.append(Chart.CANDLE_DOWN if not up else Chart.CANDLE_UP)
        else:
            vol_colors.append(Chart.CANDLE_UP if up else Chart.CANDLE_DOWN)

    vol_plot = mpf.make_addplot(df["Volume"], type="bar", panel=1,
                                color=vol_colors, alpha=0.75)

    all_addplots = ema_addplots + marker_plots + [vol_plot]

    # ── mplfinance style ──
    style = mpf.make_mpf_style(
        base_mpf_style="nightclouds",
        marketcolors=mpf.make_marketcolors(
            up=Chart.CANDLE_UP,   down=Chart.CANDLE_DOWN,
            edge={"up": Chart.CANDLE_UP, "down": Chart.CANDLE_DOWN},
            wick={"up": Chart.WICK_UP,   "down": Chart.WICK_DOWN},
            volume="inherit",
        ),
        facecolor=Chart.BACKGROUND, figcolor=Chart.BACKGROUND,
        gridcolor=Chart.GRID_COLOR, gridstyle="--",
        rc={"axes.labelcolor": "#e0e0e0",
            "xtick.color":     "#9e9e9e",
            "ytick.color":     "#9e9e9e"},
    )

    title = (f"{symbol}   {currency}{float(df['Close'].iloc[-1]):.2f}"
             f"   VCP Grade: {grade}   Score: {vcp.get('vcp_score', '?')}/11")

    fig, axes = mpf.plot(
        df, type="candle", style=style,
        addplot=all_addplots,
        volume=False,
        panel_ratios=Chart.PANEL_RATIOS,
        figsize=Chart.FIGSIZE,
        title=title,
        returnfig=True,
        tight_layout=True,
    )

    ax_price = axes[0]
    ax_vol   = axes[2]   # mplfinance inserts a spacer panel at index 1

    # ── Contraction bands ──
    for i, c in enumerate(contractions):
        hd, ld = c["high_date"], c["low_date"]
        if ld < df.index[0]:
            continue
        hd_c = max(hd, df.index[0])
        ld_c = min(ld, df.index[-1])
        try:
            x0 = df.index.get_loc(hd_c) if hd_c in df.index else df.index.searchsorted(hd_c)
            x1 = df.index.get_loc(ld_c) if ld_c in df.index else df.index.searchsorted(ld_c)
        except Exception:
            continue
        if x0 >= x1:
            continue

        color  = Chart.BAND_COLORS[i % len(Chart.BAND_COLORS)]
        band_h = c["top_close"] - c["low_price"]
        rect   = plt.Rectangle(
            (x0 - 0.4, c["low_price"]), (x1 - x0 + 0.8), band_h,
            linewidth=1.2, edgecolor=color, facecolor=color,
            alpha=0.12, zorder=2)
        ax_price.add_patch(rect)

        ax_price.text(
            (x0 + x1) / 2, c["low_price"] + band_h / 2,
            f"C{i + 1}\n{c['contraction_pct']:.1f}%",
            color=color, fontsize=7.5, ha="center", va="center",
            fontweight="bold", zorder=5,
            bbox=dict(boxstyle="round,pad=0.25", facecolor=Chart.BACKGROUND,
                      edgecolor=color, alpha=0.75, linewidth=0.8))

    # ── Pivot line ──
    if pivot:
        ax_price.axhline(pivot, color=Chart.PIVOT_COLOR, linewidth=1.4,
                         linestyle="--", alpha=0.9, zorder=6)
        ax_price.text(
            n - 1, pivot * 1.003,
            f"  Pivot {currency}{pivot:.2f}  ← buy above",
            color=Chart.PIVOT_COLOR, fontsize=8.5, va="bottom",
            fontweight="bold", zorder=7)

    # ── Grade badge ──
    ax_price.text(
        0.01, 0.985,
        f"  Grade: {grade}   Score: {vcp.get('vcp_score', '?')}/11  ",
        transform=ax_price.transAxes,
        color=grade_color, fontsize=12, fontweight="bold",
        va="top", ha="left",
        bbox=dict(boxstyle="round,pad=0.4", facecolor=Chart.BACKGROUND,
                  edgecolor=grade_color, linewidth=1.5, alpha=0.85))

    # ── RS annotation ──
    rs_txt = (f"RS vs {_benchmark_name(symbol)}: {rs_value:+.1f}%"
              if rs_value is not None else "RS: N/A")
    ax_price.text(0.01, 0.915, rs_txt,
                  transform=ax_price.transAxes,
                  color="#ce93d8", fontsize=8.5, va="top")

    # ── Volume panel ──
    ax_vol.set_facecolor(Chart.BACKGROUND)
    ax_vol.set_ylabel("Volume", color="#9e9e9e", fontsize=8)
    if vol_dry_up:
        ax_vol.text(0.01, 0.92, "Vol dry-up confirmed",
                    transform=ax_vol.transAxes,
                    color="#4caf50", fontsize=8, fontweight="bold", va="top")
    else:
        ratio_txt = f"{vol_ratio:.2f}x" if vol_ratio is not None else "N/A"
        ax_vol.text(0.01, 0.92,
                    f"Vol ratio: {ratio_txt} avg (need ≤{Chart.__dict__.get('MIN_VOLUME_DRY_UP', 0.9)}x)",
                    transform=ax_vol.transAxes,
                    color="#ff7043", fontsize=8, va="top")

    # ── Trend template footer ──
    tt_ok = trend.get("all_pass", False)
    if tt_ok:
        tt_txt = (f"Trend Template: PASS  |  "
                  f"MA50={currency}{trend.get('ma50', '?')}  "
                  f"MA150={currency}{trend.get('ma150', '?')}  "
                  f"MA200={currency}{trend.get('ma200', '?')}  |  "
                  f"+{trend.get('pct_above_52w_low', '?')}% above 52w low  "
                  f"-{trend.get('pct_below_52w_high', '?')}% below 52w high")
    else:
        tt_txt = "Trend Template: FAIL"
    ax_price.text(0.5, 0.008, tt_txt,
                  transform=ax_price.transAxes,
                  color="#a5d6a7" if tt_ok else "#ef9a9a",
                  fontsize=7.5, ha="center", va="bottom", alpha=0.9)

    # ── Legend ──
    ema_legend_handles += [
        mlines.Line2D([], [], marker="v", color="w",
                      markerfacecolor=Chart.SWING_HIGH_COLOR,
                      markersize=7, linestyle="None", label="Swing high"),
        mlines.Line2D([], [], marker="^", color="w",
                      markerfacecolor=Chart.SWING_LOW_COLOR,
                      markersize=7, linestyle="None", label="Swing low"),
    ]
    ax_price.legend(handles=ema_legend_handles, loc="upper right",
                    fontsize=7, facecolor=Chart.BACKGROUND, edgecolor="#333",
                    labelcolor="#e0e0e0", ncol=4, framealpha=0.85)

    fig.patch.set_facecolor(Chart.BACKGROUND)
    plt.savefig(save_path, dpi=Chart.DPI, bbox_inches="tight",
                facecolor=Chart.BACKGROUND, edgecolor="none")
    plt.close(fig)
    plt.close("all")
    return save_path
