# Stock Price Monitor Telegram Bot

A 24/7 stock price monitoring bot that sends Telegram alerts when prices breach your set limits.

## Features
- Set upper and lower price limits for any stock
- Receive instant Telegram notifications when limits are breached
- Manage alerts via Telegram commands
- Check current stock prices
- Automatic hourly cooldown between repeated alerts
- Persistent storage (alerts survive bot restarts)

## Setup Instructions

### 1. Install Python Dependencies
```bash
pip install -r requirements.txt
```

### 2. Set Your Telegram Bot Token
Replace `YOUR_BOT_TOKEN` with your actual bot token:

```bash
export TELEGRAM_BOT_TOKEN='YOUR_BOT_TOKEN'
```

To make it permanent, add it to your `~/.bashrc` or `~/.bash_profile`:
```bash
echo "export TELEGRAM_BOT_TOKEN='YOUR_BOT_TOKEN'" >> ~/.bashrc
source ~/.bashrc
```

### 3. Run the Bot
```bash
python stock_monitor_bot.py
```

## Running 24/7 on Your NUC

### Option 1: Using systemd (Recommended)

Create a systemd service file:
```bash
sudo nano /etc/systemd/system/stock-monitor.service
```

Add this content (replace `YOUR_USERNAME` and paths):
```ini
[Unit]
Description=Stock Price Monitor Bot
After=network.target

[Service]
Type=simple
User=YOUR_USERNAME
WorkingDirectory=/home/YOUR_USERNAME/stock-monitor
Environment="TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN"
ExecStart=/usr/bin/python3 /home/YOUR_USERNAME/stock-monitor/stock_monitor_bot.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Enable and start the service:
```bash
sudo systemctl enable stock-monitor
sudo systemctl start stock-monitor
sudo systemctl status stock-monitor
```

View logs:
```bash
sudo journalctl -u stock-monitor -f
```

### Option 2: Using screen (Simple)
```bash
screen -S stock-monitor
python stock_monitor_bot.py
# Press Ctrl+A then D to detach
# Reattach with: screen -r stock-monitor
```

### Option 3: Using nohup
```bash
nohup python stock_monitor_bot.py > stock_monitor.log 2>&1 &
```

## Bot Commands

### /start or /help
Shows welcome message and all available commands

### /set SYMBOL LOWER UPPER
Set price alerts for a stock
- `SYMBOL`: Stock ticker (e.g., AAPL, TSLA, GOOGL)
- `LOWER`: Lower price limit
- `UPPER`: Upper price limit

Example: `/set AAPL 150 180`

### /list
View all your active alerts with current prices

### /remove SYMBOL
Remove an alert for a specific stock

Example: `/remove AAPL`

### /price SYMBOL
Check the current price of any stock

Example: `/price TSLA`

## How It Works

1. **Set Alerts**: Use `/set` command to define price limits
2. **Monitoring**: Bot checks prices every 2 minutes
3. **Alerts**: You receive a Telegram message when:
   - Price drops to or below lower limit 🔴
   - Price rises to or above upper limit 🟢
4. **Cooldown**: Same alert won't repeat for 1 hour (prevents spam)
5. **Persistence**: All alerts are saved to `stock_alerts.json`

## Stock Symbols

Use Yahoo Finance ticker symbols:
- Apple: AAPL
- Tesla: TSLA
- Microsoft: MSFT
- Google: GOOGL
- Amazon: AMZN
- NVIDIA: NVDA
- Meta: META

For international stocks, add exchange suffix:
- Tata Motors (India): TATAMOTORS.NS
- Toyota (Japan): 7203.T
- Unilever (London): ULVR.L

## File Structure

```
stock-monitor/
├── stock_monitor_bot.py    # Main bot code
├── requirements.txt         # Python dependencies
├── stock_alerts.json       # Your alerts (auto-created)
└── README.md               # This file
```

## Monitoring and Maintenance

### Check if bot is running (systemd)
```bash
sudo systemctl status stock-monitor
```

### Restart bot
```bash
sudo systemctl restart stock-monitor
```

### Stop bot
```bash
sudo systemctl stop stock-monitor
```

### View real-time logs
```bash
sudo journalctl -u stock-monitor -f
```

## Troubleshooting

### Bot doesn't respond
1. Check if bot is running: `sudo systemctl status stock-monitor`
2. Verify token is correct
3. Check logs: `sudo journalctl -u stock-monitor -n 50`

### Stock symbol not found
- Verify symbol on Yahoo Finance website
- Use correct exchange suffix for non-US stocks

### No alerts received
1. Check `/list` to verify alert is set
2. Ensure current price is outside your limits
3. Check if you received an alert in the last hour (cooldown period)

## Resource Usage

Typical usage on your NUC:
- CPU: <1% (mostly idle)
- RAM: ~50-100MB
- Network: Minimal (API calls every 2 minutes)
- Disk: <1MB (for alerts storage)

Perfect for 24/7 operation on your Intel N95 NUC!

## Notes

- Prices update every 2 minutes
- Market hours depend on the exchange (NYSE, NASDAQ, etc.)
- Bot works 24/7 but receives price data only when markets are open
- Data provided by Yahoo Finance (free, no API key needed)
