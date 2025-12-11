"""
Portfolio Command Handlers
Telegram commands for portfolio management
"""

import logging
from telegram import Update
from telegram.ext import ContextTypes
from portfolio_manager import get_portfolio

logger = logging.getLogger(__name__)

# This will be set by main bot
get_stock_price = None


def set_price_getter(price_getter_func):
    """Set the price getter function from main bot"""
    global get_stock_price
    get_stock_price = price_getter_func


async def buy_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /buy command: /buy SYMBOL SHARES PRICE"""
    try:
        if len(context.args) != 3:
            await update.message.reply_text(
                "Usage: /buy SYMBOL SHARES PRICE\n\n"
                "Example: /buy AAPL 10 150.50\n"
                "This records buying 10 shares of Apple at $150.50"
            )
            return

        symbol = context.args[0].upper()
        shares = float(context.args[1])
        price = float(context.args[2])

        if shares <= 0 or price <= 0:
            await update.message.reply_text("❌ Shares and price must be positive numbers!")
            return

        # Get portfolio and add position
        portfolio = get_portfolio(update.effective_chat.id)
        portfolio.add_position(symbol, shares, price)

        total_cost = shares * price

        message = (
            f"✅ *Purchase Recorded*\n\n"
            f"Symbol: {symbol}\n"
            f"Shares: {shares}\n"
            f"Price: ${price:.2f}\n"
            f"Total Cost: ${total_cost:.2f}\n\n"
            f"Use /portfolio to see your complete portfolio"
        )

        await update.message.reply_text(message, parse_mode='Markdown')
        logger.info(f"Buy recorded: {symbol} {shares} @ ${price} by chat {update.effective_chat.id}")

    except ValueError as e:
        await update.message.reply_text(f"❌ Invalid input: {str(e)}")
    except Exception as e:
        logger.error(f"Error in buy_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def sell_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /sell command: /sell SYMBOL SHARES PRICE"""
    try:
        if len(context.args) != 3:
            await update.message.reply_text(
                "Usage: /sell SYMBOL SHARES PRICE\n\n"
                "Example: /sell AAPL 5 175.00\n"
                "This records selling 5 shares of Apple at $175.00"
            )
            return

        symbol = context.args[0].upper()
        shares = float(context.args[1])
        price = float(context.args[2])

        if shares <= 0 or price <= 0:
            await update.message.reply_text("❌ Shares and price must be positive numbers!")
            return

        # Get portfolio and remove position
        portfolio = get_portfolio(update.effective_chat.id)
        realized_pl = portfolio.remove_position(symbol, shares, price)

        total_proceeds = shares * price
        pl_emoji = "📈" if realized_pl >= 0 else "📉"

        message = (
            f"✅ *Sale Recorded* {pl_emoji}\n\n"
            f"Symbol: {symbol}\n"
            f"Shares: {shares}\n"
            f"Price: ${price:.2f}\n"
            f"Total Proceeds: ${total_proceeds:.2f}\n"
            f"Realized P&L: ${realized_pl:+.2f}\n\n"
            f"Use /portfolio to see your updated portfolio"
        )

        await update.message.reply_text(message, parse_mode='Markdown')
        logger.info(f"Sell recorded: {symbol} {shares} @ ${price}, P&L: ${realized_pl:.2f}")

    except ValueError as e:
        await update.message.reply_text(f"❌ {str(e)}")
    except Exception as e:
        logger.error(f"Error in sell_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def portfolio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /portfolio command: Show complete portfolio with analysis"""
    try:
        portfolio = get_portfolio(update.effective_chat.id)

        if not portfolio.positions:
            await update.message.reply_text(
                "📭 Your portfolio is empty!\n\n"
                "Use /buy to add your first position:\n"
                "/buy AAPL 10 150.50"
            )
            return

        # Send "calculating..." message
        calc_msg = await update.message.reply_text("📊 Calculating portfolio...")

        # Calculate portfolio value
        portfolio_value = portfolio.calculate_portfolio_value(get_stock_price)

        if not portfolio_value:
            await calc_msg.edit_text("❌ Error calculating portfolio values")
            return

        # Build message
        total_value = portfolio_value['total_value']
        total_cost = portfolio_value['total_cost']
        total_pl = portfolio_value['total_pl']
        total_pl_pct = portfolio_value['total_pl_pct']

        pl_emoji = "📈" if total_pl >= 0 else "📉"

        message = f"📊 *Your Portfolio* {pl_emoji}\n\n"
        message += f"*Total Value:* ${total_value:,.2f}\n"
        message += f"*Cost Basis:* ${total_cost:,.2f}\n"
        message += f"*Profit/Loss:* ${total_pl:+,.2f} ({total_pl_pct:+.2f}%)\n\n"

        # AUD conversion (approximate)
        aud_rate = 1.5  # Rough estimate, could make this dynamic
        message += f"≈ ${total_value * aud_rate:,.2f} AUD\n\n"

        message += "*Holdings:*\n"
        for pos in portfolio_value['positions']:
            pl_icon = "✅" if pos['unrealized_pl'] >= 0 else "❌"
            message += (
                f"{pl_icon} *{pos['symbol']}*: {pos['shares']:.2f} shares\n"
                f"   ${pos['current_value']:,.2f} ({pos['unrealized_pl_pct']:+.1f}%)\n"
            )

        message += "\n*Sector Breakdown:*\n"
        for sector, data in sorted(portfolio_value['sector_breakdown'].items(),
                                   key=lambda x: x[1]['percentage'], reverse=True):
            pct = data['percentage']
            bar_length = int(pct / 5)  # 20 chars max for 100%
            bar = "█" * bar_length
            message += f"{sector}: {pct:.1f}% {bar}\n"

        # Diversification analysis
        analysis = portfolio.analyze_diversification(portfolio_value)
        if analysis:
            message += f"\n*Diversification Score:* {analysis['diversification_score']}/100\n"

            if analysis['warnings']:
                message += "\n⚠️ *Warnings:*\n"
                for warning in analysis['warnings'][:3]:  # Limit to 3
                    message += f"• {warning}\n"

            if analysis['recommendations']:
                message += "\n💡 *Recommendations:*\n"
                for rec in analysis['recommendations'][:3]:  # Limit to 3
                    message += f"• {rec}\n"

        await calc_msg.edit_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in portfolio_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def positions_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /positions command: Show detailed position info"""
    try:
        if len(context.args) != 1:
            await update.message.reply_text(
                "Usage: /positions SYMBOL\n\n"
                "Example: /positions AAPL\n"
                "Shows detailed information about your AAPL position"
            )
            return

        symbol = context.args[0].upper()
        portfolio = get_portfolio(update.effective_chat.id)

        detail = portfolio.get_position_detail(symbol)
        if not detail:
            await update.message.reply_text(f"❌ You don't own any {symbol}")
            return

        position = detail['position']
        current_price = get_stock_price(symbol)

        if not current_price:
            await update.message.reply_text(f"❌ Could not fetch price for {symbol}")
            return

        shares = position['shares']
        cost_basis = position['cost_basis']
        current_value = shares * current_price
        total_cost = shares * cost_basis
        unrealized_pl = current_value - total_cost
        unrealized_pl_pct = (unrealized_pl / total_cost) * 100

        pl_emoji = "📈" if unrealized_pl >= 0 else "📉"

        message = f"{pl_emoji} *Position: {symbol}*\n\n"
        message += f"*Shares:* {shares:.2f}\n"
        message += f"*Cost Basis:* ${cost_basis:.2f}\n"
        message += f"*Current Price:* ${current_price:.2f}\n\n"
        message += f"*Total Cost:* ${total_cost:,.2f}\n"
        message += f"*Current Value:* ${current_value:,.2f}\n"
        message += f"*Unrealized P&L:* ${unrealized_pl:+,.2f} ({unrealized_pl_pct:+.2f}%)\n\n"
        message += f"*Sector:* {detail['sector']}\n\n"

        # Trade history for this symbol
        message += "*Trade History:*\n"
        for trade in position.get('trades', [])[-5:]:  # Last 5 trades
            trade_type = trade['type']
            emoji = "🟢" if trade_type == "BUY" else "🔴"
            date = trade['date'].split('T')[0]  # Just the date part
            message += f"{emoji} {trade_type}: {trade['shares']:.2f} @ ${trade['price']:.2f} ({date})\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in positions_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")


async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle /history command: Show all trade history"""
    try:
        portfolio = get_portfolio(update.effective_chat.id)
        trades = portfolio.get_trade_history()

        if not trades:
            await update.message.reply_text("📭 No trade history yet!")
            return

        message = "📜 *Trade History*\n\n"

        # Show last 20 trades
        for trade in trades[:20]:
            trade_type = trade['type']
            emoji = "🟢" if trade_type == "BUY" else "🔴"
            date = trade['date'].split('T')[0]

            message += (
                f"{emoji} {trade_type} {trade['symbol']}: "
                f"{trade['shares']:.2f} @ ${trade['price']:.2f} ({date})\n"
            )

            # Show realized P&L for sells
            if trade_type == "SELL" and 'realized_pl' in trade:
                pl = trade['realized_pl']
                message += f"   P&L: ${pl:+.2f}\n"

        if len(trades) > 20:
            message += f"\n_Showing 20 of {len(trades)} trades_"

        await update.message.reply_text(message, parse_mode='Markdown')

    except Exception as e:
        logger.error(f"Error in history_command: {e}")
        await update.message.reply_text(f"❌ Error: {str(e)}")