"""
Market Alerts Module
Provides automatic alerts for:
- Market open/close notifications
- Unusual trading volume alerts
"""

import time
import logging
import requests
from datetime import datetime, time as dt_time
from threading import Thread

logger = logging.getLogger(__name__)


class MarketAlerts:
    def __init__(self, bot_token, chat_ids):
        """
        Initialize market alerts

        Args:
            bot_token: Telegram bot token
            chat_ids: List of chat IDs to send alerts to
        """
        self.bot_token = bot_token
        self.chat_ids = chat_ids if isinstance(chat_ids, list) else [chat_ids]
        self.market_open_sent_today = False
        self.market_close_sent_today = False
        self.volume_baselines = {}  # Store average volumes for stocks

    def send_message(self, message):
        """Send message to all registered chat IDs"""
        for chat_id in self.chat_ids:
            try:
                url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
                data = {
                    'chat_id': chat_id,
                    'text': message,
                    'parse_mode': 'Markdown'
                }
                response = requests.post(url, json=data, timeout=10)
                if response.status_code == 200:
                    logger.info(f"Market alert sent to chat {chat_id}")
                else:
                    logger.error(f"Failed to send alert: {response.status_code}")
            except Exception as e:
                logger.error(f"Error sending market alert: {e}")

    def is_market_day(self):
        """Check if today is a market day (Monday-Friday)"""
        return datetime.now().weekday() < 5  # 0-4 is Mon-Fri

    def check_market_hours(self):
        """Check and send market open/close alerts"""
        if not self.is_market_day():
            return

        now = datetime.now()
        current_time = now.time()

        # US Market times (EST/EDT)
        # Market opens at 9:30 AM EST
        # Alert 5 minutes before: 9:25 AM
        market_open_alert_time = dt_time(9, 25)
        market_open_time = dt_time(9, 30)

        # Market closes at 4:00 PM EST
        # Alert 5 minutes before: 3:55 PM
        market_close_alert_time = dt_time(15, 55)
        market_close_time = dt_time(16, 0)

        # Check if we should send market open alert
        if (market_open_alert_time <= current_time < market_open_time and
                not self.market_open_sent_today):
            message = (
                "🔔 *Market Opening Soon*\n\n"
                "The US stock market opens in 5 minutes (9:30 AM EST)\n"
                "Get ready! 📈"
            )
            self.send_message(message)
            self.market_open_sent_today = True
            logger.info("Market open alert sent")

        # Check if we should send market close alert
        if (market_close_alert_time <= current_time < market_close_time and
                not self.market_close_sent_today):
            message = (
                "🔔 *Market Closing Soon*\n\n"
                "The US stock market closes in 5 minutes (4:00 PM EST)\n"
                "Last chance to make trades! 📉"
            )
            self.send_message(message)
            self.market_close_sent_today = True
            logger.info("Market close alert sent")

        # Reset flags at midnight
        if current_time.hour == 0 and current_time.minute < 5:
            self.market_open_sent_today = False
            self.market_close_sent_today = False

    def get_stock_volume(self, symbol):
        """Get current volume for a stock"""
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }

        try:
            url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
            response = requests.get(url, headers=headers, timeout=10)

            if response.status_code == 200:
                data = response.json()

                if data.get('chart') and data['chart'].get('result'):
                    result = data['chart']['result'][0]

                    # Get volume from indicators
                    if 'indicators' in result and 'quote' in result['indicators']:
                        quote = result['indicators']['quote'][0]
                        if 'volume' in quote and quote['volume']:
                            volumes = [v for v in quote['volume'] if v is not None]
                            if volumes:
                                current_volume = volumes[-1]
                                avg_volume = sum(volumes) / len(volumes)
                                return current_volume, avg_volume
        except Exception as e:
            logger.debug(f"Error getting volume for {symbol}: {e}")

        return None, None

    def check_unusual_volume(self, stock_alerts):
        """
        Check for unusual trading volume
        Alert if volume is 2x or more than average
        """
        if not self.is_market_day():
            return

        now = datetime.now()
        current_time = now.time()

        # Only check during market hours (9:30 AM - 4:00 PM EST)
        market_open = dt_time(9, 30)
        market_close = dt_time(16, 0)

        if not (market_open <= current_time <= market_close):
            return

        for symbol in stock_alerts.keys():
            try:
                current_volume, avg_volume = self.get_stock_volume(symbol)

                if current_volume and avg_volume and avg_volume > 0:
                    volume_ratio = current_volume / avg_volume

                    # Alert if volume is 2x or more than average
                    if volume_ratio >= 2.0:
                        # Check if we already alerted for this stock today
                        today = datetime.now().date().isoformat()
                        alert_key = f"{symbol}_{today}"

                        if alert_key not in self.volume_baselines:
                            message = (
                                f"📊 *Unusual Volume Alert: {symbol}*\n\n"
                                f"Current volume is {volume_ratio:.1f}x the average!\n"
                                f"Current: {current_volume:,.0f}\n"
                                f"Average: {avg_volume:,.0f}\n\n"
                                f"Something big might be happening! 🚨"
                            )
                            self.send_message(message)
                            self.volume_baselines[alert_key] = True
                            logger.info(f"Unusual volume alert sent for {symbol}: {volume_ratio:.1f}x")

                # Small delay between stocks
                time.sleep(2)

            except Exception as e:
                logger.error(f"Error checking volume for {symbol}: {e}")

    def monitor(self, stock_alerts_getter):
        """
        Main monitoring loop

        Args:
            stock_alerts_getter: Function that returns current stock_alerts dict
        """
        logger.info("Market alerts monitoring started")

        while True:
            try:
                # Check market hours every minute
                self.check_market_hours()

                # Check unusual volume every 5 minutes during market hours
                if datetime.now().minute % 5 == 0:
                    stock_alerts = stock_alerts_getter()
                    if stock_alerts:
                        self.check_unusual_volume(stock_alerts)

                # Wait 1 minute before next check
                time.sleep(60)

            except Exception as e:
                logger.error(f"Error in market alerts loop: {e}")
                time.sleep(60)


def start_market_alerts(bot_token, chat_ids, stock_alerts_getter):
    """
    Start market alerts in a background thread

    Args:
        bot_token: Telegram bot token
        chat_ids: List of chat IDs to send alerts to
        stock_alerts_getter: Function that returns current stock_alerts dict
    """
    market_alerts = MarketAlerts(bot_token, chat_ids)
    monitor_thread = Thread(
        target=market_alerts.monitor,
        args=(stock_alerts_getter,),
        daemon=True
    )
    monitor_thread.start()
    logger.info("Market alerts thread started")
    return market_alerts