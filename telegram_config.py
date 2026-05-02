"""
Telegram Configuration
Get your bot token from: https://t.me/BotFather
Get your chat ID from: https://t.me/userinfobot
"""

# Your Telegram Bot Token (from @BotFather)
TELEGRAM_BOT_TOKEN = "YOUR_BOT_TOKEN_HERE"

# Your Chat ID where alerts will be sent
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID_HERE"

# Market timing (US ET)
# Scanner will run at these times (24-hour format)
MARKET_OPEN_TIME = "10:00"      # 30 mins after market opens (9:30 AM)
MARKET_CLOSE_TIME = "15:30"     # 30 mins before market closes (4:00 PM)

# Timezone
TIMEZONE = "US/Eastern"

# Setup filter levels (which grades to report)
# Options: "A", "B", "C", "D" or "all"
SETUP_GRADES = ["A", "B"]  # Report only Grade A and B setups

# Enable/Disable notifications
NOTIFY_ON_TREND_PASS = True
NOTIFY_ON_VCP_ONLY = False
NOTIFY_ON_VALID_SETUPS_ONLY = True  # Grade A+B with trend template

print("✓ Telegram config loaded")
