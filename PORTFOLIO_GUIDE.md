# Portfolio Management Features

## New Commands

### Recording Trades

**Buy a stock:**
```
/buy AAPL 10 150.50
```
Records buying 10 shares of Apple at $150.50

**Sell a stock:**
```
/sell AAPL 5 175.00
```
Records selling 5 shares of Apple at $175.00
- Shows realized profit/loss
- Updates your position

### Viewing Your Portfolio

**Complete portfolio overview:**
```
/portfolio
```
Shows:
- Total portfolio value
- Total profit/loss
- All positions with current values
- Sector breakdown (with visual bars!)
- Diversification score (0-100)
- Warnings about concentration
- Recommendations for better diversification

**Detailed position view:**
```
/positions AAPL
```
Shows detailed info for one stock:
- Number of shares
- Cost basis
- Current price and value
- Unrealized P&L
- Trade history for that stock

**Trade history:**
```
/history
```
Shows all your buys and sells (last 20 trades)

## How It Works

### Position Tracking
- Bot tracks shares you own and your cost basis
- Automatically calculates average cost when you buy more
- Updates position when you sell
- All stored locally in `portfolio_data.json`

### Profit/Loss Calculation
- **Unrealized P&L**: (Current Price - Cost Basis) × Shares
- **Realized P&L**: (Sell Price - Cost Basis) × Shares Sold
- Shown both in dollars and percentage

### Diversification Analysis

**Score breakdown:**
- **80-100**: Excellent diversification ✅
- **60-79**: Good diversification 👍
- **40-59**: Moderate risk ⚠️
- **0-39**: High risk ❌

**What it checks:**
- Sector concentration (warns if >40% in one sector)
- Number of positions (recommends 10-15)
- Presence of bonds and commodities
- Single position dominance

**Warnings you might see:**
- "❌ Technology: 75% - HIGHLY CONCENTRATED!"
- "⚠️ Only 3 positions - Low diversification"
- "⚠️ AAPL is 45% of portfolio"

**Recommendations:**
- "Reduce Technology exposure to below 60%"
- "Add bonds (TLT, AGG) for stability"
- "Add commodities (GLD) as inflation hedge"
- "Consider adding more positions (target: 10-15)"

## Example Usage

**Build your portfolio:**
```
/buy AAPL 10 150.00
✅ Purchase Recorded
Symbol: AAPL
Shares: 10
Price: $150.00
Total Cost: $1,500.00

/buy MSFT 5 300.00
✅ Purchase Recorded

/buy TLT 15 95.00
✅ Purchase Recorded (bonds for diversification!)

/buy GLD 8 180.00
✅ Purchase Recorded (commodities!)
```

**Check your portfolio:**
```
/portfolio

📊 Your Portfolio 📈

Total Value: $7,890.00
Cost Basis: $7,125.00
Profit/Loss: +$765.00 (+10.74%)

≈ $11,835.00 AUD

Holdings:
✅ AAPL: 10.00 shares
   $1,750.00 (+16.7%)
✅ MSFT: 5.00 shares
   $1,625.00 (+8.3%)
✅ TLT: 15.00 shares
   $1,425.00 (+0.0%)
✅ GLD: 8.00 shares
   $1,520.00 (+5.6%)

Sector Breakdown:
Technology: 42.8% ████████
Bonds: 18.1% ███
Commodities: 19.3% ███
Finance: 19.8% ███

Diversification Score: 85/100

💡 Recommendations:
• Well diversified across asset classes
• Consider adding international exposure
```

**Sell some shares:**
```
/sell AAPL 5 175.00

✅ Sale Recorded 📈
Symbol: AAPL
Shares: 5
Price: $175.00
Total Proceeds: $875.00
Realized P&L: +$125.00
```

**Check specific position:**
```
/positions AAPL

📈 Position: AAPL

Shares: 5.00
Cost Basis: $150.00
Current Price: $175.00

Total Cost: $750.00
Current Value: $875.00
Unrealized P&L: +$125.00 (+16.67%)

Sector: Technology

Trade History:
🟢 BUY: 10.00 @ $150.00 (2025-12-11)
🔴 SELL: 5.00 @ $175.00 (2025-12-11)
```

## Supported Symbols

All Yahoo Finance symbols work:

**US Stocks:** AAPL, MSFT, GOOGL, TSLA, etc.
**ETFs:** SPY, QQQ, TLT, AGG, GLD, etc.
**ASX Stocks:** BHP.AX, CBA.AX, WES.AX, etc.

The bot automatically knows the sector for 100+ common stocks!

## Data Storage

- All portfolio data stored in `portfolio_data.json`
- Separate portfolio for each Telegram user
- Persists across bot restarts
- Backup this file to keep your data!

## Tips

1. **Record all trades** - Even if you forget, you can backfill
2. **Check /portfolio regularly** - Track your progress
3. **Follow recommendations** - They're based on modern portfolio theory
4. **Aim for 70+ diversification score** - Reduces risk significantly
5. **Don't over-diversify** - 10-15 positions is sweet spot

## Files

Upload these files to your NUC:
- `portfolio_manager.py` - Core portfolio logic
- `portfolio_commands.py` - Telegram command handlers
- `stock_monitor_bot_v3.py` - Updated main bot

Then restart: `sudo systemctl restart stock-monitor`

Enjoy tracking your portfolio! 📊📈