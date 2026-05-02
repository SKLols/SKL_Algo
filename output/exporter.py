"""
output/exporter.py — Excel and CSV export for scan results.
"""
import os
import pandas as pd

from config import Export, OUTPUT_DIR

os.makedirs(OUTPUT_DIR, exist_ok=True)


def export_vcp_to_excel(results: list,
                         filename: str | None = None) -> pd.DataFrame:
    """
    Write all Trend+VCP passing results to an Excel file.

    Only rows where trend_pass=True AND is_vcp=True are exported.
    Returns the DataFrame that was written (empty DataFrame if nothing passed).
    """
    if filename is None:
        filename = Export.VCP_FILENAME

    valid = [r for r in results
             if r.get("trend_pass") and r.get("is_vcp") and not r.get("error")]

    rows = []
    for r in valid:
        rows.append({
            "Symbol"            : r["symbol"],
            "Price"             : r["current_price"],
            "Trend_Pass"        : r["trend_pass"],
            "MA50"              : r["ma50"],
            "MA150"             : r["ma150"],
            "MA200"             : r["ma200"],
            "EMA_10"            : r.get("ema_10"),
            "EMA_20"            : r.get("ema_20"),
            "EMA_50"            : r.get("ema_50"),
            "EMA_150"           : r.get("ema_150"),
            "EMA_200"           : r.get("ema_200"),
            "RS"                : r.get("rs"),
            "RS_Index"          : r.get("rs_index"),
            "Pct_Above_52w_Low" : r["pct_above_52w_low"],
            "Pct_Below_52w_High": r["pct_below_52w_high"],
            "Down_From_52w_High": r.get("down_from_52w_high"),
            "Within_5pct_High"  : r.get("within_5pct_high"),
            "Is_VCP"            : r["is_vcp"],
            "VCP_Quality"       : r["vcp_quality"],
            "Num_Contractions"  : r["num_contractions"],
            "Final_Contraction" : r["final_contraction_pct"],
            "Volume_Dry_Up"     : r["volume_dry_up"],
            "Vol_Ratio"         : r["vol_ratio"],
            "Pivot_Price"       : r["pivot_price"],
            "VCP_Score"         : r.get("vcp_score"),
            "VCP_Bonus"         : r.get("vcp_score_bonus"),
        })

    df_out      = pd.DataFrame(rows)
    output_path = os.path.join(OUTPUT_DIR, filename)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name=Export.SHEET_VCP)

    print(f"\n  Results saved → {output_path}  ({len(valid)} valid Trend+VCP rows)")
    return df_out

def export_all_to_excel(results: list, filename: str = "scan_results.xlsx"):
    output_path = os.path.join(OUTPUT_DIR, filename)
    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:

        def _write(rows, sheet):
            if rows:
                pd.DataFrame(rows).to_excel(writer, index=False, sheet_name=sheet)

        _write([r for r in results if r.get("trend_pass") and r.get("is_vcp")],        "VCP")
        _write([r for r in results if r.get("trend_pass") and r.get("is_darvas")],     "Darvas")
        _write([r for r in results if r.get("trend_pass") and r.get("is_powerplay")],  "PowerPlay")
        _write([r for r in results if r.get("trend_pass") and r.get("is_breakout")],   "Breakout")
        _write([r for r in results if r.get("trend_pass") and r.get("is_cup_handle")], "CupHandle")

    print(f"\n  All setups saved → {output_path}")


def export_breadth_to_excel(breadth_rows: list,
                             filename: str | None = None) -> pd.DataFrame:
    """
    Write market breadth results (one row per stock with trend pass/fail detail)
    to an Excel file. Called by market_breadth.py.
    """
    if filename is None:
        filename = Export.BREADTH_FILENAME

    df_out      = pd.DataFrame(breadth_rows)
    output_path = os.path.join(OUTPUT_DIR, filename)

    with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
        df_out.to_excel(writer, index=False, sheet_name=Export.SHEET_BREADTH)

    print(f"\n  Breadth data saved → {output_path}  ({len(breadth_rows)} rows)")
    return df_out
