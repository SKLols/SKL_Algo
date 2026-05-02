# 📱 Telegram Automation Setup Guide

Complete guide to set up automated VCP scanner notifications on Telegram with daily alerts.

## Overview

The scanner will automatically run **2 times daily**:
- **10:00 AM ET** — 30 minutes after market open (9:30 AM)
- **15:30 (3:30 PM) ET** — 30 minutes before market close (4:00 PM)

Results are sent to Telegram with:
- ✅ Summary statistics
- 📊 Grade A & B setups listed
- 📁 Excel file attachment with full results

---

## Step 1: Create Telegram Bot

### 1a. Open Telegram and message BotFather
1. Open Telegram app
2. Search for `@BotFather` (official Telegram bot creator)
3. Start chat and send: `/newbot`

### 1b. Follow prompts to create your bot
- **Name**: e.g., "VCP Scanner Bot"
- **Username**: e.g., "my_vcp_scanner_bot" (must end with `_bot`)

### 1c. Get your Bot Token
- BotFather will send a message with your token
- **Example**: `123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11`
- ⚠️ **Keep this secret!** Don't share it

---

## Step 2: Get Your Chat ID

### Option A: Using @userinfobot (Easiest)
1. Search for `@userinfobot` on Telegram
2. Start chat and click `START`
3. It will show you your **ID** (e.g., `987654321`)

### Option B: Send a message to your bot
1. Message your newly created bot
2. Go to: `https://api.telegram.org/bot<YOUR_TOKEN>/getUpdates`
   - Replace `<YOUR_TOKEN>` with your actual token
3. Look for `"id": <your_chat_id>`

---

## Step 3: Update Configuration

### Edit `telegram_config.py`

```python
# Your Telegram Bot Token (from @BotFather)
TELEGRAM_BOT_TOKEN = "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11"

# Your Chat ID where alerts will be sent
TELEGRAM_CHAT_ID = "987654321"

# Market timing (US ET) - adjust if needed
MARKET_OPEN_TIME = "10:00"      # 30 mins after market opens
MARKET_CLOSE_TIME = "15:30"     # 30 mins before market closes

# Setup filter levels (Grade A and B recommended)
SETUP_GRADES = ["A", "B"]
```

---

## Step 4: Install Dependencies

```bash
pip install -r requirements.txt
```

This installs:
- `python-telegram-bot` — Telegram bot library
- `schedule` — Job scheduling
- `pytz` — Timezone support
- `requests` — HTTP requests

---

## Step 5: Test Setup

```bash
python scheduler.py --test
```

**Expected output:**
```
======================================================================
🧪 Testing VCP Scanner + Telegram Setup
======================================================================

1️⃣  Testing Telegram connection...
   ✓ Telegram connection successful!

2️⃣  Running quick test scan...
   ✓ Scanner initialized successfully!

✅ Setup test passed! Ready to use.
```

If test passes, you should receive a test message on Telegram. ✅

---

## Step 6: Setup Windows Task Scheduler (Automatic Runs)

### Option A: Automatic Setup (Recommended)
```bash
python setup_scheduler.py
```

This creates 2 scheduled tasks in Windows Task Scheduler:
- **VCP Scanner - Market Open** → Daily at 10:00 AM
- **VCP Scanner - Market Close** → Daily at 15:30 (3:30 PM)

### Option B: Manual Setup
1. Open **Task Scheduler** (Win + R → `taskschd.msc`)
2. Create two tasks:

**Task 1: Market Open**
- **Name**: VCP Scanner - Market Open
- **Trigger**: Daily at 10:00 AM
- **Action**: Run script `run_scanner_open.vbs`
- **Location**: Scanner project directory

**Task 2: Market Close**
- **Name**: VCP Scanner - Market Close
- **Trigger**: Daily at 15:30 (3:30 PM)
- **Action**: Run script `run_scanner_close.vbs`

---

## Step 7: Run Manually (for testing)

Test a single run before enabling scheduled tasks:

```bash
# Run market open scan
python scheduler.py --run-once open

# Run market close scan
python scheduler.py --run-once close
```

---

## Step 8: Monitor and Verify

### Check if tasks are running
1. Open Task Scheduler
2. Find your tasks under `Task Scheduler Library`
3. Right-click → **View** to see last run status

### Verify Telegram messages
- You should receive alerts at the scheduled times
- Excel file will be attached to each report

---

## 🚨 Troubleshooting

### ❌ "Telegram connection failed"
- ✅ Check `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID` in `telegram_config.py`
- ✅ Verify token from BotFather is correct
- ✅ Ensure internet connection is active

### ❌ "Tasks not running at scheduled times"
- ✅ Check Task Scheduler → History tab for errors
- ✅ Verify Python path is correct in `.vbs` files
- ✅ Check that "Run whether user is logged in or not" is enabled

### ❌ "Excel file not attached"
- ✅ Verify `output/` folder exists and has write permissions
- ✅ Check file size (Telegram has 50 MB limit)

### ❌ "No valid setups found"
- ✅ Lower the `SETUP_GRADES` threshold: `["A", "B", "C", "D"]`
- ✅ Adjust market timing if running outside trading hours

---

## 📧 Additional Setup (Optional)

### Customize Telegram Messages
Edit `telegram_notifier.py` → `send_scan_report()` to change:
- Which grades to show
- Message format
- Additional filters

### Change Market Timezone
Edit `telegram_config.py`:
```python
TIMEZONE = "US/Eastern"  # Change to your timezone
```

Available timezones: `pytz.all_timezones`

### Disable Scheduled Tasks
```bash
# View all tasks
schtasks /query /tn "VCP Scanner*"

# Delete a task
schtasks /delete /tn "VCP Scanner - Market Open" /f
```

---

## 📊 Telegram Report Format

Each report includes:
```
📊 VCP Scanner Report
[timestamp]

Summary:
• Total scanned: 500
• Trend Template passed: 245
• VCP detected: 89
• Valid Setups (Trend + VCP): 34
• Grade A/B Setups: 12

🟢 Grade A Setups (5):
AAPL    $180.45 | Pivot: $185.20 | Final: 8.3%
MSFT    $305.12 | Pivot: $312.50 | Final: 7.1%
...

🟡 Grade B Setups (7):
GOOGL   $142.30 | Pivot: $148.90 | Final: 9.2%
...

Full results attached in Excel file
```

---

## ✅ Verification Checklist

- [ ] Bot token obtained from @BotFather
- [ ] Chat ID obtained
- [ ] `telegram_config.py` updated with credentials
- [ ] Dependencies installed: `pip install -r requirements.txt`
- [ ] Test passed: `python scheduler.py --test`
- [ ] Task Scheduler configured
- [ ] First manual run successful: `python scheduler.py --run-once open`
- [ ] Received Telegram message with Excel attachment

---

## 🎯 Next Steps

1. **Start the scheduler manually** to verify it works:
   ```bash
   python scheduler.py
   ```
   (Ctrl+C to stop)

2. **Enable Windows Task Scheduler** to run automatically each day

3. **Monitor first few runs** to ensure messages arrive correctly

4. **Adjust settings** as needed (grades, times, message format)

---

**Questions?** Check the code comments in:
- `scheduler.py` — Main automation logic
- `telegram_notifier.py` — Message formatting
- `telegram_config.py` — Configuration options

Happy scanning! 🚀
