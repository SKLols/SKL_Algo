"""
Windows Task Scheduler Setup
Run this to automatically setup scheduled tasks in Windows Task Scheduler
"""

import os
import sys
import subprocess
from pathlib import Path

def create_task_scheduler_bat():
    """Create batch file for Windows Task Scheduler to execute."""
    scanner_dir = Path(__file__).parent
    python_exe = sys.executable
    scheduler_script = scanner_dir / "scheduler.py"
    
    bat_content = f'''@echo off
cd /d "{scanner_dir}"
"{python_exe}" "{scheduler_script}" --run-once %1
pause
'''
    
    bat_file = scanner_dir / "run_scanner.bat"
    with open(bat_file, 'w') as f:
        f.write(bat_content)

    print(f"[OK] Created: {bat_file}")
    return bat_file


def create_vbs_wrapper():
    """Create VBS wrapper to run tasks silently (no command window)."""
    scanner_dir = Path(__file__).parent
    python_exe = sys.executable
    scheduler_script = scanner_dir / "scheduler.py"

    vbs_open = f'''Set objShell = CreateObject("WScript.Shell")
objShell.Run "{python_exe} ""{scheduler_script}"" --run-once open", 0, False
'''

    vbs_close = f'''Set objShell = CreateObject("WScript.Shell")
objShell.Run "{python_exe} ""{scheduler_script}"" --run-once close", 0, False
'''

    vbs_live_picks = f'''Set objShell = CreateObject("WScript.Shell")
objShell.Run "{python_exe} ""{scheduler_script}"" --run-once live_picks", 0, False
'''

    vbs_file_open = scanner_dir / "run_scanner_open.vbs"
    vbs_file_close = scanner_dir / "run_scanner_close.vbs"
    vbs_file_live_picks = scanner_dir / "run_scanner_live_picks.vbs"

    with open(vbs_file_open, 'w') as f:
        f.write(vbs_open)
    with open(vbs_file_close, 'w') as f:
        f.write(vbs_close)
    with open(vbs_file_live_picks, 'w') as f:
        f.write(vbs_live_picks)

    print(f"[OK] Created: {vbs_file_open}")
    print(f"[OK] Created: {vbs_file_close}")
    print(f"[OK] Created: {vbs_file_live_picks}")

    return vbs_file_open, vbs_file_close, vbs_file_live_picks


def setup_task_scheduler():
    """Setup tasks in Windows Task Scheduler."""
    print("\n" + "="*70)
    print("Setting up Windows Task Scheduler")
    print("="*70)

    scanner_dir = Path(__file__).parent
    vbs_open, vbs_close, vbs_live_picks = create_vbs_wrapper()

    import telegram_config

    # Market Open Task (6:00 AM CET/CEST = ~30 mins after NSE opens)
    print(f"\n1) Creating market open task ({telegram_config.MARKET_OPEN_TIME} {telegram_config.TIMEZONE} - Indian market)...")
    cmd_open = f'''schtasks /create /tn "VCP Scanner - Market Open" /tr "{vbs_open}" /sc daily /st {telegram_config.MARKET_OPEN_TIME} /f'''

    try:
        result = subprocess.run(cmd_open, shell=True, capture_output=True, text=True)
        if result.returncode == 0 or "already exists" in result.stderr:
            print("   [OK] Market open task created/updated")
        else:
            print(f"   [FAIL] Failed: {result.stderr}")
    except Exception as e:
        print(f"   [FAIL] Error: {e}")

    # Market Close Task (11:00 AM CET/CEST = ~30 mins before NSE closes)
    print(f"\n2) Creating market close task ({telegram_config.MARKET_CLOSE_TIME} {telegram_config.TIMEZONE} - Indian market)...")
    cmd_close = f'''schtasks /create /tn "VCP Scanner - Market Close" /tr "{vbs_close}" /sc daily /st {telegram_config.MARKET_CLOSE_TIME} /f'''

    try:
        result = subprocess.run(cmd_close, shell=True, capture_output=True, text=True)
        if result.returncode == 0 or "already exists" in result.stderr:
            print("   [OK] Market close task created/updated")
        else:
            print(f"   [FAIL] Failed: {result.stderr}")
    except Exception as e:
        print(f"   [FAIL] Error: {e}")

    # Live Picks Task (shortly after market close)
    print(f"\n3) Creating live picks task ({telegram_config.LIVE_PICKS_TIME} {telegram_config.TIMEZONE})...")
    cmd_live_picks = f'''schtasks /create /tn "VCP Scanner - Live Picks" /tr "{vbs_live_picks}" /sc daily /st {telegram_config.LIVE_PICKS_TIME} /f'''

    try:
        result = subprocess.run(cmd_live_picks, shell=True, capture_output=True, text=True)
        if result.returncode == 0 or "already exists" in result.stderr:
            print("   [OK] Live picks task created/updated")
        else:
            print(f"   [FAIL] Failed: {result.stderr}")
    except Exception as e:
        print(f"   [FAIL] Error: {e}")

    print("\n" + "="*70)
    print("Tasks setup complete!")
    print("="*70)
    print("\nYou can verify in Windows Task Scheduler:")
    print("  1. Open Task Scheduler")
    print("  2. Look for 'VCP Scanner - Market Open', 'VCP Scanner - Market Close',")
    print("     and 'VCP Scanner - Live Picks'")
    print("  3. Right-click -> Properties to adjust time/settings if needed")
    print("\nTasks will run daily at (Germany timezone):")
    print(f"  - {telegram_config.MARKET_OPEN_TIME} - Market Open Scan (~30 min after NSE opens at 9:15 AM IST)")
    print(f"  - {telegram_config.MARKET_CLOSE_TIME} - Market Close Scan (~30 min before NSE closes at 3:30 PM IST)")
    print(f"  - {telegram_config.LIVE_PICKS_TIME} - Live Picks watchlist (top_sector_all_methods / "
          "top_sector_vcp_only / top_sector_powerplay_only)")


if __name__ == "__main__":
    setup_task_scheduler()
