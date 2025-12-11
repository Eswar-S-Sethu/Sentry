# Market Alerts Update

## New Automatic Features

Your bot now has two new automatic alert features that run in the background:

### 1. Market Open/Close Alerts 🔔
- **5 minutes before market open** (9:25 AM EST) - You'll get a notification
- **5 minutes before market close** (3:55 PM EST) - You'll get a notification
- Only on weekdays (Monday-Friday)
- **No command needed** - happens automatically!

### 2. Unusual Volume Alerts 📊
- Monitors all your stocks during market hours (9:30 AM - 4:00 PM EST)
- Alerts you when volume is **2x or more** than average
- Checks every 5 minutes
- Only alerts once per day per stock
- **No command needed** - happens automatically!

## Installation

1. **Upload both files to your NUC:**
   - `market_alerts.py` (new file)
   - `stock_monitor_bot_v3.py` (updated main file)

2. **Place them in the same directory:**
   ```bash
   cd ~/Sentry
   # Upload both files here
   ```

3. **Restart the bot:**
   ```bash
   sudo systemctl restart stock-monitor
   sudo systemctl status stock-monitor
   ```

4. **Check logs to verify:**
   ```bash
   sudo journalctl -u stock-monitor -f
   ```

   You should see:
   ```
   Market alerts enabled for 1 chat(s)
   Market alerts thread started
   ```

## How It Works

- **Market hours alerts**: Checks every minute, sends 5 min before open/close
- **Volume alerts**: Checks every 5 minutes during market hours
- **Automatic**: No commands needed, just works in the background
- **Smart**: Won't spam you - only one alert per event per day

## Example Alerts You'll Receive

**Market Opening:**
```
🔔 Market Opening Soon

The US stock market opens in 5 minutes (9:30 AM EST)
Get ready! 📈
```

**Market Closing:**
```
🔔 Market Closing Soon

The US stock market closes in 5 minutes (4:00 PM EST)
Last chance to make trades! 📉
```

**Unusual Volume:**
```
📊 Unusual Volume Alert: AAPL

Current volume is 3.2x the average!
Current: 45,234,567
Average: 14,123,456

Something big might be happening! 🚨
```

## Notes

- All times are in **US Eastern Time (EST/EDT)**
- Market alerts only happen on **weekdays** (no weekends)
- Volume alerts only during **market hours** (9:30 AM - 4:00 PM)
- If you have multiple stocks, you'll get volume alerts for each one independently

## Troubleshooting

**Not receiving alerts?**
1. Make sure you have at least one stock alert set: `/set AAPL 150 200`
2. Check the bot is running: `sudo systemctl status stock-monitor`
3. Check logs: `sudo journalctl -u stock-monitor -n 50`

**Getting too many volume alerts?**
The threshold is 2x average volume. You can adjust this in `market_alerts.py` line 130:
```python
if volume_ratio >= 2.0:  # Change 2.0 to 3.0 for less sensitive
```

Enjoy your automated market alerts! 🚀