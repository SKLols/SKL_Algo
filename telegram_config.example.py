"""
Telegram Configuration — copy this file to telegram_config.py and fill in your values.

Steps:
  1. Create a bot:  message @BotFather on Telegram → /newbot → copy the token
  2. Get your chat ID: message @userinfobot on Telegram → copy the id number
  3. cp telegram_config.example.py telegram_config.py
  4. Replace the placeholder values below with your real credentials
"""

# Your Telegram Bot Token (from @BotFather)
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Your Chat ID where alerts will be sent (from @userinfobot)
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"

# Market timing (Indian market — displayed in Germany timezone)
# Indian market opens at 9:15 AM IST, closes at 3:30 PM IST
# Converted to Germany time (CET/CEST, handles DST automatically):
#   - 30 mins after open  (9:45 AM IST) ≈ 5:15 AM CET / 6:15 AM CEST
#   - 30 mins before close (3:00 PM IST) ≈ 10:30 AM CET / 11:30 AM CEST
MARKET_OPEN_TIME  = "06:00"   # ~30 mins after NSE opens  (Germany time)
MARKET_CLOSE_TIME = "11:00"   # ~30 mins before NSE closes (Germany time)

# Timezone (Germany)
TIMEZONE = "Europe/Berlin"

# Setup filter levels (which grades to report)
# Options: "A", "B", "C", "D" or "all"
SETUP_GRADES = ["A", "B"]   # Report only Grade A and B setups

# Manual Telegram command to trigger an immediate scan
TELEGRAM_MANUAL_RUN_COMMAND = "/run_manual"

# Poll interval for Telegram command checks (seconds)
TELEGRAM_COMMAND_POLL_INTERVAL = 20

# Enable/Disable notifications
NOTIFY_ON_TREND_PASS       = True
NOTIFY_ON_VCP_ONLY         = False
NOTIFY_ON_VALID_SETUPS_ONLY = True  # Grade A+B with trend template
