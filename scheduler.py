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
from output.exporter import export_all_to_excel as export_to_excel
from live_picks import generate_and_send as run_live_picks_scan


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
        self.update_offset = None
        self.scan_running = False
        self.live_picks_running = False
        
    def run_scan(self, scan_type: str = "market_open"):
        """Execute full scan pipeline and send results to Telegram."""
        if self.scan_running:
            print("[WARN] Scan already running, skipping new request.")
            return
        self.scan_running = True
        try:
            current_time = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{'='*70}")
            print(f"VCP Scanner started - {scan_type.upper()}")
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
            
            print(f"\n[OK] Scan complete: {len(valid_setups)} valid setups found ({len(grade_a)} Grade A, {len(grade_b)} Grade B)")
            
            # Send to Telegram
            print("Sending results to Telegram...")
            self.notifier.send_scan_report(
                results,
                output_file=excel_path,
                grades_to_show=telegram_config.SETUP_GRADES
            )
            
            print("[OK] Telegram notification sent!")

        except Exception as e:
            print(f"[FAIL] Scan error: {e}")
            error_msg = f"❌ VCP Scanner Error ({scan_type}):\n{str(e)}"
            self.notifier.send_alert("Scanner Error", error_msg)
        finally:
            self.scan_running = False

    def run_live_picks(self):
        """
        Separate daily alert: today's top-10 picks from the 3 backtested
        sector/RS selection strategies (live_picks.py). Independent of
        run_scan() above - its own Telegram message, its own Excel file,
        its own error handling, so a failure here never blocks or is
        blocked by the original scanner job.
        """
        if self.live_picks_running:
            print("[WARN] Live picks scan already running, skipping new request.")
            return
        self.live_picks_running = True
        try:
            current_time = datetime.now(self.timezone).strftime("%Y-%m-%d %H:%M:%S")
            print(f"\n{'='*70}")
            print(f"Live picks scan started")
            print(f"   Time: {current_time}")
            print(f"{'='*70}")

            run_live_picks_scan()

            print("[OK] Live picks sent to Telegram!")

        except Exception as e:
            print(f"[FAIL] Live picks error: {e}")
            error_msg = f"Live Picks Scanner Error:\n{str(e)}"
            self.notifier.send_alert("Live Picks Error", error_msg)
        finally:
            self.live_picks_running = False

    def schedule_jobs(self):
        """Setup daily scan jobs at specified times."""
        print("\nScheduling VCP scanner jobs...")
        print(f"   Market Open (30 min after):  {telegram_config.MARKET_OPEN_TIME} {telegram_config.TIMEZONE}")
        print(f"   Market Close (30 min before): {telegram_config.MARKET_CLOSE_TIME} {telegram_config.TIMEZONE}")
        print(f"   Live picks (daily watchlist): {telegram_config.LIVE_PICKS_TIME} {telegram_config.TIMEZONE}")

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

        # Schedule the live picks watchlist (top_sector_all_methods /
        # top_sector_vcp_only / top_sector_powerplay_only), shortly after close
        schedule.every().day.at(telegram_config.LIVE_PICKS_TIME).do(
            self.run_live_picks
        )

        print("[OK] Jobs scheduled!")
        print("\nScheduler running. Press Ctrl+C to stop.\n")
    
    def poll_telegram_commands(self):
        """Check Telegram updates for manual run requests."""
        updates = self.notifier.get_updates(
            offset=self.update_offset,
            timeout=telegram_config.TELEGRAM_COMMAND_POLL_INTERVAL
        )
        if not updates:
            return

        for update in updates:
            self.update_offset = update["update_id"] + 1
            message = update.get("message") or update.get("edited_message")
            if not message:
                continue
            chat = message.get("chat", {})
            chat_id = str(chat.get("id"))
            text = message.get("text", "")
            if chat_id != str(telegram_config.TELEGRAM_CHAT_ID):
                continue
            if text.strip().lower().startswith(telegram_config.TELEGRAM_MANUAL_RUN_COMMAND):
                self.notifier.send_message("✅ Manual scan command received. Starting scan now.")
                self.run_scan(scan_type="manual")

    def run_scheduler(self):
        """Start the scheduler loop."""
        self.schedule_jobs()
        
        # Keep scheduler running
        next_poll = time.time()
        poll_interval = telegram_config.TELEGRAM_COMMAND_POLL_INTERVAL
        while True:
            schedule.run_pending()
            if time.time() >= next_poll:
                self.poll_telegram_commands()
                next_poll = time.time() + poll_interval
            time.sleep(1)  # Check frequently for scheduled jobs and commands


def run_scheduler_daemon():
    """Entry point for running scheduler as daemon."""
    scheduler = VCPScheduler()
    scheduler.run_scheduler()


def test_setup():
    """Test Telegram connection and scanner."""
    print("\n" + "="*70)
    print("Testing VCP Scanner + Telegram Setup")
    print("="*70)
    
    # Test Telegram
    print("\n1) Testing Telegram connection...")
    if test_telegram_connection(
        telegram_config.TELEGRAM_BOT_TOKEN,
        telegram_config.TELEGRAM_CHAT_ID
    ):
        print("   [OK] Telegram connection successful!")
    else:
        print("   [FAIL] Telegram connection failed!")
        print("   Make sure TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID are set correctly in telegram_config.py")
        return False
    
    # Test scanner
    print("\n2) Running quick test scan...")
    try:
        scheduler = VCPScheduler()
        print("   [OK] Scanner initialized successfully!")
    except Exception as e:
        print(f"   [FAIL] Scanner initialization failed: {e}")
        return False
    
    print("\n[OK] Setup test passed! Ready to use.\n")
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
        choices=["open", "close", "live_picks"],
        help="Run scanner once (for market open, close, or the live_picks watchlist)"
    )

    args = parser.parse_args()

    if args.test:
        test_setup()
    elif args.run_once == "live_picks":
        scheduler = VCPScheduler()
        scheduler.run_live_picks()
    elif args.run_once:
        scheduler = VCPScheduler()
        scheduler.run_scan(scan_type=f"market_{args.run_once}")
    else:
        run_scheduler_daemon()
