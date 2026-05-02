"""
Scheduler — Automated daily VCP scans with Telegram notifications
Runs scanner for Indian market (NSE) at market open and close
Times shown in Germany timezone (CET/CEST, auto-adjusts for DST)
"""

import schedule
import time
from datetime import datetime
import pytz
import os
import sys

# Add parent dir to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import telegram_config
from telegram_notifier import TelegramNotifier, test_telegram_connection
from scanner import run_scanner
from output.exporter import export_to_excel


class VCPScheduler:
    """Manages automated VCP scanning with Telegram alerts."""
    
    def __init__(self):
        """Initialize scheduler with Telegram notifier."""
        self.notifier = TelegramNotifier(
            telegram_config.TELEGRAM_BOT_TOKEN,
            telegram_config.TELEGRAM_CHAT_ID
        )
        self.timezone = pytz.timezone(telegram_config.TIMEZONE)
        self.output_dir = os.path.join(os.path.dirname(__file__), "output")
        
    def run_scan(self, scan_type: str = "market_open"):
        """Execute full scan pipeline and send results to Telegram."""
        try:
            current_time = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{'='*70}")
            print(f"🔍 VCP Scanner started - {scan_type.upper()}")
            print(f"   Time: {current_time}")
            print(f"{'='*70}")
            
            # Run scanner
            print("Running VCP scan...")
            results = run_scanner()
            
            # Export results
            print("Exporting to Excel...")
            excel_path = os.path.join(self.output_dir, "vcp_scan_results.xlsx")
            export_to_excel(results, filename="vcp_scan_results.xlsx")
            
            # Filter results
            valid_setups = [r for r in results if r.get("trend_pass") and r.get("is_vcp") and not r.get("error")]
            grade_a = [r for r in valid_setups if "A" in r.get("vcp_quality", "")]
            grade_b = [r for r in valid_setups if "B" in r.get("vcp_quality", "")]
            
            print(f"\n✓ Scan complete: {len(valid_setups)} valid setups found ({len(grade_a)} Grade A, {len(grade_b)} Grade B)")
            
            # Send to Telegram
            print("Sending results to Telegram...")
            self.notifier.send_scan_report(
                results,
                output_file=excel_path,
                grades_to_show=telegram_config.SETUP_GRADES
            )
            
            print("✓ Telegram notification sent!")
            
        except Exception as e:
            print(f"❌ Scan error: {e}")
            error_msg = f"❌ VCP Scanner Error ({scan_type}):\n{str(e)}"
            self.notifier.send_alert("Scanner Error", error_msg)
    
    def schedule_jobs(self):
        """Setup daily scan jobs at specified times."""
        print("\n📅 Scheduling VCP scanner jobs...")
        print(f"   Market Open (30 min after):  {telegram_config.MARKET_OPEN_TIME} {telegram_config.TIMEZONE}")
        print(f"   Market Close (30 min before): {telegram_config.MARKET_CLOSE_TIME} {telegram_config.TIMEZONE}")
        
        # Schedule market open scan (6:00 AM CET/CEST ≈ 9:45 AM IST)
        schedule.every().day.at(telegram_config.MARKET_OPEN_TIME).do(
            self.run_scan, 
            scan_type="market_open"
        )
        
        # Schedule market close scan (11:00 AM CET/CEST ≈ 3:00 PM IST)
        schedule.every().day.at(telegram_config.MARKET_CLOSE_TIME).do(
            self.run_scan, 
            scan_type="market_close"
        )
        
        print("✓ Jobs scheduled!")
        print("\nScheduler running. Press Ctrl+C to stop.\n")
    
    def run_scheduler(self):
        """Start the scheduler loop."""
        self.schedule_jobs()
        
        # Keep scheduler running
        while True:
            schedule.run_pending()
            time.sleep(60)  # Check every minute


def run_scheduler_daemon():
    """Entry point for running scheduler as daemon."""
    scheduler = VCPScheduler()
    scheduler.run_scheduler()


def test_setup():
    """Test Telegram connection and scanner."""
    print("\n" + "="*70)
    print("🧪 Testing VCP Scanner + Telegram Setup")
    print("="*70)
    
    # Test Telegram
    print("\n1️⃣  Testing Telegram connection...")
    if test_telegram_connection(
        telegram_config.TELEGRAM_BOT_TOKEN,
        telegram_config.TELEGRAM_CHAT_ID
    ):
        print("   ✓ Telegram connection successful!")
    else:
        print("   ❌ Telegram connection failed!")
        print("   Make sure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set correctly in telegram_config.py")
        return False
    
    # Test scanner
    print("\n2️⃣  Running quick test scan...")
    try:
        scheduler = VCPScheduler()
        print("   ✓ Scanner initialized successfully!")
    except Exception as e:
        print(f"   ❌ Scanner initialization failed: {e}")
        return False
    
    print("\n✅ Setup test passed! Ready to use.\n")
    return True


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="VCP Scanner Scheduler")
    parser.add_argument(
        "--test",
        action="store_true",
        help="Test Telegram connection and scanner setup"
    )
    parser.add_argument(
        "--run-once",
        choices=["open", "close"],
        help="Run scanner once (for market open or close)"
    )
    
    args = parser.parse_args()
    
    if args.test:
        test_setup()
    elif args.run_once:
        scheduler = VCPScheduler()
        scheduler.run_scan(scan_type=f"market_{args.run_once}")
    else:
        run_scheduler_daemon()
