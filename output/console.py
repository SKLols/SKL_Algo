"""
output/console.py — Console printing for scan results.

print_result() is identical to the original monolithic script.
"""


def print_result(r: dict) -> None:
    """Print a full scan result for one stock to stdout."""
    sep = "─" * 60
    print(f"\n{sep}")

    if r.get("error"):
        print(f"  {r['symbol']}  ERROR: {r['error']}")
        return

    currency   = "₹" if r["symbol"].endswith(".NS") else "$"
    trend_icon = "✓" if r["trend_pass"] else "✗"
    vcp_icon   = "✓" if r["is_vcp"]    else "✗"

    print(f"  {r['symbol']}   {currency}{r['current_price']}")
    print(f"  Trend Template : [{trend_icon}]  "
          f"MA50={currency}{r['ma50']}  "
          f"MA150={currency}{r['ma150']}  "
          f"MA200={currency}{r['ma200']}")
    print(f"  52w: +{r['pct_above_52w_low']}% above low  |  "
          f"-{r['pct_below_52w_high']}% below high")

    rs_str = f"{r['rs']:+.1f}%" if r.get("rs") is not None else "N/A"
    print(f"  RS ({r.get('rs_index', 'N/A')}): {rs_str}")

    print(f"  VCP Pattern    : [{vcp_icon}]  Quality: {r['vcp_quality']}")
    print(f"  Contractions   : {r['num_contractions']}  |  "
          f"Final contraction: {r['final_contraction_pct']}%")
    print(f"  Volume dry-up  : {'YES' if r['volume_dry_up'] else 'NO'}  "
          f"(ratio: {r['vol_ratio']}x avg)")
    print(f"  Pivot price    : {currency}{r['pivot_price']}")

    if r.get("contractions"):
        print(f"\n  Contraction history:")
        for i, c in enumerate(r["contractions"], 1):
            print(f"    C{i}: {c['high_date'].date()} {currency}{c['high_price']} → "
                  f"{c['low_date'].date()} {currency}{c['low_price']}  "
                  f"({c['contraction_pct']}% drop)  vol_avg={c['avg_volume']:,}")

    if r.get("vcp_notes"):
        print(f"\n  Notes:")
        for note in r["vcp_notes"]:
            print(f"    · {note}")


def print_summary(results: list) -> None:
    """Print the end-of-run summary table."""
    print("\n" + "=" * 60)
    print("  SUMMARY")
    print("=" * 60)

    passed_trend = [r for r in results if r.get("trend_pass")]
    passed_vcp   = [r for r in results if r.get("is_vcp")]
    valid_setups = [r for r in results if r.get("trend_pass") and r.get("is_vcp")]
    a_quality    = [r for r in valid_setups if str(r.get("vcp_quality", "")).startswith("A")]

    print(f"  Trend Template passed : {len(passed_trend)}/{len(results)}")
    print(f"  VCP detected          : {len(passed_vcp)}/{len(results)}")
    print(f"  Trend+VCP setups      : {len(valid_setups)}/{len(results)}")
    print(f"  Grade A setups        : {len(a_quality)}/{len(results)}")

    if a_quality:
        print(f"\n  TOP SETUPS (Grade A VCP):")
        for r in a_quality:
            cur = "₹" if r["symbol"].endswith(".NS") else "$"
            print(f"    {r['symbol']:20s}  {cur}{r['current_price']}  "
                  f"Pivot: {cur}{r['pivot_price']}  "
                  f"Final contraction: {r['final_contraction_pct']}%")

    if valid_setups:
        print(f"\n  VALID SETUPS (Trend + VCP):")
        for r in valid_setups:
            cur = "₹" if r["symbol"].endswith(".NS") else "$"
            print(f"    {r['symbol']:20s}  {cur}{r['current_price']}  "
                  f"Pivot: {cur}{r['pivot_price']}  "
                  f"Quality: {r['vcp_quality']}")
    elif passed_vcp:
        print(f"\n  VCP SETUPS FOUND (trend template failed for some):")
        for r in passed_vcp:
            cur = "₹" if r["symbol"].endswith(".NS") else "$"
            print(f"    {r['symbol']:20s}  {cur}{r['current_price']}  "
                  f"Pivot: {cur}{r['pivot_price']}  "
                  f"Quality: {r['vcp_quality']}")
