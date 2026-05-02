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
    
    print(f"✓ Created: {bat_file}")
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
    
    vbs_file_open = scanner_dir / "run_scanner_open.vbs"
    vbs_file_close = scanner_dir / "run_scanner_close.vbs"
    
    with open(vbs_file_open, 'w') as f:
        f.write(vbs_open)
    with open(vbs_file_close, 'w') as f:
        f.write(vbs_close)
    
    print(f"✓ Created: {vbs_file_open}")
    print(f"✓ Created: {vbs_file_close}")
    
    return vbs_file_open, vbs_file_close


def setup_task_scheduler():
    """Setup tasks in Windows Task Scheduler."""
    print("\n" + "="*70)
    print("📅 Setting up Windows Task Scheduler")
    print("="*70)
    
    scanner_dir = Path(__file__).parent
    vbs_open, vbs_close = create_vbs_wrapper()
    
    # Market Open Task (10:00 AM)
    print("\n1️⃣  Creating market open task (10:00 AM)...")
    cmd_open = f'''schtasks /create /tn "VCP Scanner - Market Open" /tr "{vbs_open}" /sc daily /st 10:00 /f'''
    
    try:
        result = subprocess.run(cmd_open, shell=True, capture_output=True, text=True)
        if result.returncode == 0 or "already exists" in result.stderr:
            print("   ✓ Market open task created/updated")
        else:
            print(f"   ❌ Failed: {result.stderr}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    # Market Close Task (3:30 PM)
    print("\n2️⃣  Creating market close task (15:30)...")
    cmd_close = f'''schtasks /create /tn "VCP Scanner - Market Close" /tr "{vbs_close}" /sc daily /st 15:30 /f'''
    
    try:
        result = subprocess.run(cmd_close, shell=True, capture_output=True, text=True)
        if result.returncode == 0 or "already exists" in result.stderr:
            print("   ✓ Market close task created/updated")
        else:
            print(f"   ❌ Failed: {result.stderr}")
    except Exception as e:
        print(f"   ❌ Error: {e}")
    
    print("\n" + "="*70)
    print("✅ Tasks setup complete!")
    print("="*70)
    print("\nYou can verify in Windows Task Scheduler:")
    print("  1. Open Task Scheduler")
    print("  2. Look for 'VCP Scanner - Market Open' and 'VCP Scanner - Market Close'")
    print("  3. Right-click → Properties to adjust time/settings if needed")
    print("\nTasks will run daily at:")
    print("  • 10:00 AM - Market Open Scan")
    print("  • 15:30 (3:30 PM) - Market Close Scan")


if __name__ == "__main__":
    setup_task_scheduler()
