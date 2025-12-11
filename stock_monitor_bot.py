import os
import json
import time
import logging
from datetime import datetime
from threading import Thread
import requests
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Configuration file path
CONFIG_FILE = 'stock_alerts.json'

# Global storage for stock alerts
stock_alerts = {}


def get_stock_price(symbol):
    """Get stock price using Yahoo Finance API directly"""

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }

    # Method 1: Yahoo Finance Chart API
    try:
        url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get('chart') and data['chart'].get('result'):
                result = data['chart']['result'][0]

                # Try to get current price from meta
                if 'meta' in result and 'regularMarketPrice' in result['meta']:
                    price = result['meta']['regularMarketPrice']
                    if price and price > 0:
                        logger.info(f"Got price for {symbol}: ${price:.2f}")
                        return float(price)

                # Try to get from quote data
                if 'indicators' in result and 'quote' in result['indicators']:
                    quote = result['indicators']['quote'][0]
                    if 'close' in quote and quote['close']:
                        # Get last non-null close price
                        closes = [c for c in quote['close'] if c is not None]
                        if closes:
                            price = closes[-1]
                            logger.info(f"Got price for {symbol} from quote: ${price:.2f}")
                            return float(price)
    except Exception as e:
        logger.debug(f"Yahoo Chart API failed for {symbol}: {e}")

    # Method 2: Yahoo Finance Quote API
    try:
        url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={symbol}"
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get('quoteResponse') and data['quoteResponse'].get('result'):
                result = data['quoteResponse']['result'][0]

                # Try different price fields
                price = (result.get('regularMarketPrice') or
                         result.get('currentPrice') or
                         result.get('ask') or
                         result.get('bid'))

                if price and price > 0:
                    logger.info(f"Got price for {symbol} from quote API: ${price:.2f}")
                    return float(price)
    except Exception as e:
        logger.debug(f"Yahoo Quote API failed for {symbol}: {e}")

    # Method 3: Alternative endpoint
    try:
        url = f"https://query2.finance.yahoo.com/v8/finance/chart/{symbol}?interval=1d&range=1d"
        response = requests.get(url, headers=headers, timeout=10)

        if response.status_code == 200:
            data = response.json()

            if data.get('chart') and data['chart'].get('result'):
                result = data['chart']['result'][0]

                if 'meta' in result:
                    price = result['meta'].get('regularMarketPrice')
                    if price and price > 0:
                        logger.info(f"Got price for {symbol} from query2: ${price:.2f}")
                        return float(price)
    except Exception as e:
        logger.debug(f"Yahoo query2 failed for {symbol}: {e}")

    logger.error(f"All methods failed for {symbol}")
    return None


def load_alerts():
    """Load alerts from JSON file"""
    global stock_alerts
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, 'r') as f:
            stock_alerts = json.load(f)
        logger.info(f"Loaded {len(stock_alerts)} stock alerts")
    else:
        stock_alerts = {}


def save_alerts():
    """Save alerts to JSON file"""
    with open(CONFIG_FILE, 'w') as f:
        json.dump(stock_alerts, f, indent=2)
    logger.info("Alerts saved to file")


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a message when the command /start is issued."""
    welcome_message = """
🤖 *Stock Price Monitor Bot*

Commands:
/set - Set price alerts for a stock
/list - View all your alerts
/remove - Remove a stock alert
/price - Check current stock price
/help - Show this help message

*How to set alerts:*
/set AAPL 150 180
This sets alerts for Apple stock with lower limit $150 and upper limit $180

*Stock symbols:* Use Yahoo Finance symbols (e.g., AAPL, TSLA, GOOGL, MSFT)
"""
    await update.message.reply_text(welcome_message, parse_mode='Markdown')


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Send a help message"""
    await start(update, context)


async def set_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Set price alert for a stock: /set SYMBOL LOWER_LIMIT UPPER_LIMIT"""
    try:
        if len(context.args) != 3:
            await update.message.reply_text(
                "Usage: /set SYMBOL LOWER_LIMIT UPPER_LIMIT\n"
                "Example: /set AAPL 150 180"
            )
            return

        symbol = context.args[0].upper()
        lower_limit = float(context.args[1])
        upper_limit = float(context.args[2])

        if lower_limit >= upper_limit:
            await update.message.reply_text("❌ Lower limit must be less than upper limit!")
            return

        # Send "checking..." message
        checking_msg = await update.message.reply_text(f"🔍 Checking {symbol}...")

        # Verify stock symbol exists and get price
        current_price = get_stock_price(symbol)

        if current_price is None:
            await checking_msg.edit_text(
                f"❌ Could not find stock symbol: *{symbol}*\n\n"
                f"Tips:\n"
                f"• Make sure the symbol is correct (e.g., AAPL not APPLE)\n"
                f"• Use Yahoo Finance symbols\n"
                f"• Try checking the symbol on yahoo.com/finance first",
                parse_mode='Markdown'
            )
            return

        # Store alert
        stock_alerts[symbol] = {
            'lower_limit': lower_limit,
            'upper_limit': upper_limit,
            'chat_id': update.effective_chat.id,
            'last_price': current_price,
            'last_alert': None
        }
        save_alerts()

        await checking_msg.edit_text(
            f"✅ Alert set for *{symbol}*\n"
            f"Current Price: ${current_price:.2f}\n"
            f"Lower Limit: ${lower_limit:.2f}\n"
            f"Upper Limit: ${upper_limit:.2f}",
            parse_mode='Markdown'
        )
        logger.info(f"Alert set for {symbol} by chat {update.effective_chat.id}")

    except ValueError:
        await update.message.reply_text("❌ Invalid numbers! Use: /set SYMBOL LOWER_LIMIT UPPER_LIMIT")
    except Exception as e:
        logger.error(f"Error in set_alert: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def list_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """List all active alerts for this chat"""
    chat_id = update.effective_chat.id
    user_alerts = {k: v for k, v in stock_alerts.items() if v['chat_id'] == chat_id}

    if not user_alerts:
        await update.message.reply_text("📭 You have no active alerts. Use /set to create one!")
        return

    message = "📊 *Your Active Alerts:*\n\n"
    for symbol, data in user_alerts.items():
        message += f"*{symbol}*\n"
        message += f"  Last Price: ${data['last_price']:.2f}\n"
        message += f"  Lower Limit: ${data['lower_limit']:.2f}\n"
        message += f"  Upper Limit: ${data['upper_limit']:.2f}\n\n"

    await update.message.reply_text(message, parse_mode='Markdown')


async def remove_alert(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Remove a stock alert: /remove SYMBOL"""
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /remove SYMBOL\nExample: /remove AAPL")
        return

    symbol = context.args[0].upper()
    chat_id = update.effective_chat.id

    if symbol in stock_alerts and stock_alerts[symbol]['chat_id'] == chat_id:
        del stock_alerts[symbol]
        save_alerts()
        await update.message.reply_text(f"✅ Alert removed for {symbol}")
        logger.info(f"Alert removed for {symbol}")
    else:
        await update.message.reply_text(f"❌ No alert found for {symbol}")


async def check_price(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Check current price of a stock: /price SYMBOL"""
    if len(context.args) != 1:
        await update.message.reply_text("Usage: /price SYMBOL\nExample: /price AAPL")
        return

    symbol = context.args[0].upper()

    checking_msg = await update.message.reply_text(f"🔍 Fetching price for {symbol}...")

    try:
        current_price = get_stock_price(symbol)

        if current_price is None:
            await checking_msg.edit_text(
                f"❌ Could not find stock symbol: *{symbol}*\n\n"
                f"Make sure you're using the correct Yahoo Finance ticker.",
                parse_mode='Markdown'
            )
            return

        message = f"📈 *{symbol}*\n"
        message += f"Current Price: ${current_price:.2f}"

        await checking_msg.edit_text(message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error checking price for {symbol}: {e}")
        await checking_msg.edit_text(f"❌ Error fetching price for {symbol}")


def monitor_stocks(bot_token):
    """Background thread to monitor stock prices"""
    logger.info("Stock monitoring thread started")

    def send_telegram_message(chat_id, message):
        """Send message using Telegram HTTP API directly"""
        try:
            url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
            data = {
                'chat_id': chat_id,
                'text': message,
                'parse_mode': 'Markdown'
            }
            response = requests.post(url, json=data, timeout=10)
            if response.status_code == 200:
                logger.info(f"Message sent successfully to chat {chat_id}")
            else:
                logger.error(f"Failed to send message: {response.status_code}")
        except Exception as e:
            logger.error(f"Error sending Telegram message: {e}")

    while True:
        try:
            if not stock_alerts:
                time.sleep(60)
                continue

            for symbol, alert_data in list(stock_alerts.items()):
                try:
                    current_price = get_stock_price(symbol)

                    if current_price is None:
                        logger.warning(f"Could not get price for {symbol}, skipping this cycle")
                        continue

                    # Update last price
                    stock_alerts[symbol]['last_price'] = current_price

                    # Check if price breached limits
                    lower_limit = alert_data['lower_limit']
                    upper_limit = alert_data['upper_limit']
                    chat_id = alert_data['chat_id']
                    last_alert = alert_data.get('last_alert')

                    now = datetime.now().isoformat()

                    # Send alert if limits breached (and not alerted in last hour)
                    if current_price <= lower_limit:
                        if last_alert is None or (datetime.now() - datetime.fromisoformat(last_alert)).seconds > 3600:
                            message = f"🔴 *ALERT: {symbol}*\n\n"
                            message += f"Price dropped to ${current_price:.2f}\n"
                            message += f"Lower limit: ${lower_limit:.2f}\n"
                            message += f"⚠️ Price is AT or BELOW your lower limit!"

                            send_telegram_message(chat_id, message)

                            stock_alerts[symbol]['last_alert'] = now
                            save_alerts()
                            logger.info(f"Alert sent for {symbol}: price {current_price} below {lower_limit}")

                    elif current_price >= upper_limit:
                        if last_alert is None or (datetime.now() - datetime.fromisoformat(last_alert)).seconds > 3600:
                            message = f"🟢 *ALERT: {symbol}*\n\n"
                            message += f"Price rose to ${current_price:.2f}\n"
                            message += f"Upper limit: ${upper_limit:.2f}\n"
                            message += f"⚠️ Price is AT or ABOVE your upper limit!"

                            send_telegram_message(chat_id, message)

                            stock_alerts[symbol]['last_alert'] = now
                            save_alerts()
                            logger.info(f"Alert sent for {symbol}: price {current_price} above {upper_limit}")

                    # Small delay between checks to avoid rate limiting
                    time.sleep(1)

                except Exception as e:
                    logger.error(f"Error monitoring {symbol}: {e}")
                    continue

            # Save updated prices
            save_alerts()

        except Exception as e:
            logger.error(f"Error in monitoring loop: {e}")

        # Check every 30 seconds for faster updates
        time.sleep(30)


async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log errors"""
    logger.error(f"Update {update} caused error {context.error}")


def main():
    """Start the bot"""
    # Load existing alerts
    load_alerts()

    # Get token from environment variable
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        print("❌ Error: TELEGRAM_BOT_TOKEN environment variable not set!")
        print("Set it with: export TELEGRAM_BOT_TOKEN='your_token_here'")
        return

    # Create the Application
    application = Application.builder().token(token).build()

    # Register command handlers
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("set", set_alert))
    application.add_handler(CommandHandler("list", list_alerts))
    application.add_handler(CommandHandler("remove", remove_alert))
    application.add_handler(CommandHandler("price", check_price))

    # Error handler
    application.add_error_handler(error_handler)

    # Start monitoring thread
    monitor_thread = Thread(target=monitor_stocks, args=(token,), daemon=True)
    monitor_thread.start()

    # Start the Bot
    logger.info("Bot started. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == '__main__':
    main()