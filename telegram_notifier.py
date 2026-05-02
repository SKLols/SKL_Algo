"""
Telegram Notifier — Send VCP scan results to Telegram
Handles message formatting and file uploads
"""

import os
from datetime import datetime
from typing import List, Dict
import requests

class TelegramNotifier:
    """Send VCP results to Telegram with formatted messages and file attachments."""
    
    def __init__(self, bot_token: str, chat_id: str):
        """
        Args:
            bot_token: Telegram Bot API token
            chat_id: Target chat ID for messages
        """
        self.bot_token = bot_token
        self.chat_id = chat_id
        self.base_url = f"https://api.telegram.org/bot{bot_token}"
        
    def send_message(self, text: str) -> bool:
        """Send text message to Telegram chat."""
        try:
            url = f"{self.base_url}/sendMessage"
            payload = {
                "chat_id": self.chat_id,
                "text": text,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)
            if response.status_code != 200:
                print(f"❌ Telegram send_message failed: {response.status_code} {response.text}")
                return False
            return True
        except Exception as e:
            print(f"❌ Telegram message error: {e}")
            return False
    
    def send_file(self, file_path: str, caption: str = "") -> bool:
        """Send file (Excel, CSV, etc.) to Telegram."""
        try:
            if not os.path.exists(file_path):
                print(f"❌ File not found: {file_path}")
                return False
            
            url = f"{self.base_url}/sendDocument"
            with open(file_path, 'rb') as file:
                files = {'document': file}
                payload = {
                    "chat_id": self.chat_id,
                    "caption": caption,
                    "parse_mode": "HTML"
                }
                response = requests.post(url, files=files, data=payload, timeout=30)
                if response.status_code != 200:
                    print(f"❌ Telegram send_file failed: {response.status_code} {response.text}")
                    return False
                return True
        except Exception as e:
            print(f"❌ Telegram file upload error: {e}")
            return False
    
    def get_updates(self, offset: int | None = None, timeout: int = 5):
        """Poll Telegram getUpdates for incoming bot messages."""
        try:
            url = f"{self.base_url}/getUpdates"
            params = {"timeout": timeout}
            if offset is not None:
                params["offset"] = offset
            response = requests.get(url, params=params, timeout=timeout + 5)
            if response.status_code != 200:
                print(f"❌ Telegram get_updates failed: {response.status_code} {response.text}")
                return None
            data = response.json()
            if not data.get("ok"):
                print(f"❌ Telegram get_updates returned error: {data}")
                return None
            return data.get("result", [])
        except Exception as e:
            print(f"❌ Telegram get_updates error: {e}")
            return None

    def send_scan_report(self, results: List[Dict], output_file: str = None, 
                        grades_to_show: List[str] = None):
        """
        Format and send comprehensive scan report to Telegram.
        
        Args:
            results: List of scan results from scanner
            output_file: Path to Excel file to attach
            grades_to_show: Which grades to include (e.g., ["A", "B"])
        """
        if grades_to_show is None:
            grades_to_show = ["A", "B", "C", "D"]
        
        # Filter results
        valid_setups = [r for r in results if r.get("trend_pass") and r.get("is_vcp") and not r.get("error")]
        filtered_setups = [r for r in valid_setups if any(grade in r.get("vcp_quality", "") for grade in grades_to_show)]
        
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # Build main message
        message = f"""
<b>📊 VCP Scanner Report</b>
<i>{timestamp}</i>

<b>Summary:</b>
• Total scanned: {len(results)}
• Trend Template passed: {len([r for r in results if r.get('trend_pass')])}
• VCP detected: {len([r for r in results if r.get('is_vcp')])}
• <b>Valid Setups (Trend + VCP): {len(valid_setups)}</b>
• Grade A/B Setups: {len(filtered_setups)}
"""
        
        # Add Grade A setups
        grade_a = [r for r in filtered_setups if "A" in r.get("vcp_quality", "")]
        if grade_a:
            message += f"\n<b>🟢 Grade A Setups ({len(grade_a)}):</b>\n"
            for r in grade_a[:10]:  # Limit to 10 per message
                message += f"""
<code>{r['symbol']:8s}</code> ${r['current_price']:7.2f} | Pivot: ${r['pivot_price']:7.2f} | Final: {r['final_contraction_pct']:.1f}%
"""
        
        # Add Grade B setups
        grade_b = [r for r in filtered_setups if "B" in r.get("vcp_quality", "")]
        if grade_b:
            message += f"\n<b>🟡 Grade B Setups ({len(grade_b)}):</b>\n"
            for r in grade_b[:10]:
                message += f"""
<code>{r['symbol']:8s}</code> ${r['current_price']:7.2f} | Pivot: ${r['pivot_price']:7.2f} | Final: {r['final_contraction_pct']:.1f}%
"""
        
        message += f"\n<i>Full results attached in Excel file</i>"
        
        # Send message
        if self.send_message(message):
            print("✓ Main report sent to Telegram")
        else:
            print("❌ Failed to send main report")
        
        # Send Excel file if available
        if output_file and os.path.exists(output_file):
            caption = f"📈 VCP Scan Results - {timestamp}"
            if self.send_file(output_file, caption):
                print("✓ Excel file sent to Telegram")
            else:
                print("❌ Failed to send Excel file")
    
    def send_alert(self, title: str, message: str):
        """Send quick alert message."""
        alert = f"<b>🚨 {title}</b>\n{message}"
        self.send_message(alert)


def test_telegram_connection(bot_token: str, chat_id: str) -> bool:
    """Test if Telegram bot can connect and send message."""
    notifier = TelegramNotifier(bot_token, chat_id)
    test_msg = "✅ Telegram bot connection test successful!"
    return notifier.send_message(test_msg)
