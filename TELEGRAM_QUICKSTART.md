# 🤖 Telegram Automation Quick Start

## 3-Minute Setup

### 1. Get Telegram Credentials
```
1. Message @BotFather on Telegram
2. Send: /newbot
3. Name your bot: "VCP Scanner Bot"
4. Username: "my_vcp_scanner_bot"
5. Copy the token BotFather sends
6. Message @userinfobot to get your Chat ID
```

### 2. Update Config
Edit `telegram_config.py`:
```python
TELEGRAM_BOT_TOKEN = "YOUR_TOKEN_FROM_BOTFATHER"
TELEGRAM_CHAT_ID = "YOUR_ID_FROM_USERINFOBOT"
```

### 3. Install Dependencies
```bash
pip install -r requirements.txt
```

### 4. Test Connection
```bash
python scheduler.py --test
```

Should receive ✅ test message on Telegram!

### 5. Setup Automatic Runs
```bash
python setup_scheduler.py
```

This creates Windows Task Scheduler tasks to run:
- **10:00 AM** — Market Open Scan
- **3:30 PM** — Market Close Scan

---

## Commands

```bash
# Test setup
python scheduler.py --test

# Run single scan
python scheduler.py --run-once open    # Market open
python scheduler.py --run-once close   # Market close

# Run scheduler manually (Ctrl+C to stop)
python scheduler.py

# Setup Windows Task Scheduler
python setup_scheduler.py
```

---

## What You'll Receive

**2 Telegram messages per trading day:**
- ✅ Summary (total scanned, setups found, grades)
- ✅ Top Grade A & B setups listed
- ✅ Excel file with complete results

Example:
```
📊 VCP Scanner Report
2026-05-03 10:05:32

Summary:
• Total scanned: 500
• Trend Template passed: 245
• VCP detected: 89
• Valid Setups (Trend + VCP): 34
• Grade A/B Setups: 12

🟢 Grade A Setups (5):
AAPL    $180.45 | Pivot: $185.20 | Final: 8.3%
...
```

---

## Customization

Edit `telegram_config.py`:
```python
# Which grades to report
SETUP_GRADES = ["A", "B"]  # Change to ["A", "B", "C", "D"] for more

# Change market times (24-hour format)
MARKET_OPEN_TIME = "10:00"   # 30 min after market opens
MARKET_CLOSE_TIME = "15:30"  # 30 min before close

# Change timezone
TIMEZONE = "US/Eastern"  # or "US/Pacific", etc.
```

---

## Full Documentation

See `TELEGRAM_SETUP.md` for detailed setup instructions.

---

## 🚨 Troubleshooting

**No test message?**
- Check TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID
- Verify internet connection
- Try test again: `python scheduler.py --test`

**Tasks not running?**
- Open Task Scheduler, check History tab for errors
- Verify Python path in `.vbs` files
- Make sure PC doesn't sleep during market hours

**No Excel attachment?**
- Check `output/` folder has write permissions
- Verify file was created in output folder

---

Happy trading! 🚀
