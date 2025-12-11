"""
Portfolio Management Module
Tracks positions, calculates P&L, analyzes diversification
"""

import json
import os
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Sector mapping database
SECTOR_MAP = {
    # Technology
    'AAPL': 'Technology', 'MSFT': 'Technology', 'GOOGL': 'Technology', 'GOOG': 'Technology',
    'META': 'Technology', 'NVDA': 'Technology', 'AMD': 'Technology', 'INTC': 'Technology',
    'ORCL': 'Technology', 'CRM': 'Technology', 'ADBE': 'Technology', 'CSCO': 'Technology',
    'AVGO': 'Technology', 'QCOM': 'Technology', 'TXN': 'Technology', 'SHOP': 'Technology',

    # Automotive/EV
    'TSLA': 'Automotive', 'F': 'Automotive', 'GM': 'Automotive', 'RIVN': 'Automotive',
    'LCID': 'Automotive', 'NIO': 'Automotive',

    # Finance
    'JPM': 'Finance', 'BAC': 'Finance', 'WFC': 'Finance', 'C': 'Finance',
    'GS': 'Finance', 'MS': 'Finance', 'V': 'Finance', 'MA': 'Finance',
    'PYPL': 'Finance', 'SQ': 'Finance', 'BLK': 'Finance',

    # Healthcare
    'JNJ': 'Healthcare', 'UNH': 'Healthcare', 'PFE': 'Healthcare', 'ABBV': 'Healthcare',
    'TMO': 'Healthcare', 'ABT': 'Healthcare', 'CVS': 'Healthcare', 'MRK': 'Healthcare',
    'LLY': 'Healthcare', 'AMGN': 'Healthcare',

    # Consumer
    'AMZN': 'Consumer', 'WMT': 'Consumer', 'HD': 'Consumer', 'NKE': 'Consumer',
    'MCD': 'Consumer', 'SBUX': 'Consumer', 'TGT': 'Consumer', 'COST': 'Consumer',
    'LOW': 'Consumer', 'DIS': 'Consumer', 'NFLX': 'Consumer',

    # Energy
    'XOM': 'Energy', 'CVX': 'Energy', 'COP': 'Energy', 'SLB': 'Energy',
    'EOG': 'Energy', 'PSX': 'Energy', 'MPC': 'Energy',

    # Commodities/Precious Metals
    'GLD': 'Commodities', 'SLV': 'Commodities', 'GDX': 'Commodities',

    # Bonds
    'TLT': 'Bonds', 'SHY': 'Bonds', 'AGG': 'Bonds', 'BND': 'Bonds',
    'LQD': 'Bonds', 'HYG': 'Bonds', 'GOVT': 'Bonds',

    # Commodities ETFs
    'USO': 'Commodities', 'UNG': 'Commodities', 'DBA': 'Commodities',

    # ASX Stocks
    'BHP.AX': 'Mining', 'RIO.AX': 'Mining', 'FMG.AX': 'Mining',
    'CBA.AX': 'Finance', 'WBC.AX': 'Finance', 'NAB.AX': 'Finance', 'ANZ.AX': 'Finance',
    'CSL.AX': 'Healthcare', 'WES.AX': 'Consumer', 'WOW.AX': 'Consumer',
    'TLS.AX': 'Telecom', 'WDS.AX': 'Energy',
}

PORTFOLIO_FILE = 'portfolio_data.json'


class Portfolio:
    def __init__(self, chat_id):
        self.chat_id = chat_id
        self.positions = {}
        self.load_portfolio()

    def load_portfolio(self):
        """Load portfolio from JSON file"""
        if os.path.exists(PORTFOLIO_FILE):
            try:
                with open(PORTFOLIO_FILE, 'r') as f:
                    all_portfolios = json.load(f)
                    self.positions = all_portfolios.get(str(self.chat_id), {})
                logger.info(f"Loaded portfolio for chat {self.chat_id}: {len(self.positions)} positions")
            except Exception as e:
                logger.error(f"Error loading portfolio: {e}")
                self.positions = {}
        else:
            self.positions = {}

    def save_portfolio(self):
        """Save portfolio to JSON file"""
        try:
            # Load all portfolios
            all_portfolios = {}
            if os.path.exists(PORTFOLIO_FILE):
                with open(PORTFOLIO_FILE, 'r') as f:
                    all_portfolios = json.load(f)

            # Update this chat's portfolio
            all_portfolios[str(self.chat_id)] = self.positions

            # Save back
            with open(PORTFOLIO_FILE, 'w') as f:
                json.dump(all_portfolios, f, indent=2)

            logger.info(f"Saved portfolio for chat {self.chat_id}")
        except Exception as e:
            logger.error(f"Error saving portfolio: {e}")

    def add_position(self, symbol, shares, price):
        """Add or update a position (buy)"""
        symbol = symbol.upper()
        shares = float(shares)
        price = float(price)

        if symbol not in self.positions:
            # New position
            self.positions[symbol] = {
                'shares': shares,
                'cost_basis': price,
                'trades': [{
                    'type': 'BUY',
                    'shares': shares,
                    'price': price,
                    'date': datetime.now().isoformat()
                }]
            }
        else:
            # Add to existing position (average cost)
            current_shares = self.positions[symbol]['shares']
            current_cost = self.positions[symbol]['cost_basis']

            new_total_shares = current_shares + shares
            new_cost_basis = ((current_shares * current_cost) + (shares * price)) / new_total_shares

            self.positions[symbol]['shares'] = new_total_shares
            self.positions[symbol]['cost_basis'] = new_cost_basis
            self.positions[symbol]['trades'].append({
                'type': 'BUY',
                'shares': shares,
                'price': price,
                'date': datetime.now().isoformat()
            })

        self.save_portfolio()
        logger.info(f"Added position: {symbol} {shares} shares @ ${price}")

    def remove_position(self, symbol, shares, price):
        """Remove from a position (sell)"""
        symbol = symbol.upper()
        shares = float(shares)
        price = float(price)

        if symbol not in self.positions:
            raise ValueError(f"You don't own any {symbol}")

        current_shares = self.positions[symbol]['shares']

        if shares > current_shares:
            raise ValueError(f"You only own {current_shares} shares of {symbol}")

        # Calculate realized P&L
        cost_basis = self.positions[symbol]['cost_basis']
        realized_pl = (price - cost_basis) * shares

        # Update position
        new_shares = current_shares - shares

        self.positions[symbol]['trades'].append({
            'type': 'SELL',
            'shares': shares,
            'price': price,
            'date': datetime.now().isoformat(),
            'realized_pl': realized_pl
        })

        if new_shares <= 0.001:  # Close to zero, remove position
            del self.positions[symbol]
        else:
            self.positions[symbol]['shares'] = new_shares

        self.save_portfolio()
        logger.info(f"Sold position: {symbol} {shares} shares @ ${price}, P&L: ${realized_pl:.2f}")

        return realized_pl

    def get_sector(self, symbol):
        """Get sector for a symbol"""
        return SECTOR_MAP.get(symbol.upper(), 'Other')

    def calculate_portfolio_value(self, price_getter):
        """
        Calculate total portfolio value and breakdown

        Args:
            price_getter: Function that takes symbol and returns current price
        """
        if not self.positions:
            return None

        total_value = 0
        total_cost = 0
        positions_data = []
        sector_breakdown = {}

        for symbol, position in self.positions.items():
            shares = position['shares']
            cost_basis = position['cost_basis']

            # Get current price
            current_price = price_getter(symbol)
            if current_price is None:
                logger.warning(f"Could not get price for {symbol}")
                continue

            # Calculate values
            current_value = shares * current_price
            total_cost_for_position = shares * cost_basis
            unrealized_pl = current_value - total_cost_for_position
            unrealized_pl_pct = (unrealized_pl / total_cost_for_position) * 100

            total_value += current_value
            total_cost += total_cost_for_position

            # Get sector
            sector = self.get_sector(symbol)
            if sector not in sector_breakdown:
                sector_breakdown[sector] = 0
            sector_breakdown[sector] += current_value

            positions_data.append({
                'symbol': symbol,
                'shares': shares,
                'cost_basis': cost_basis,
                'current_price': current_price,
                'current_value': current_value,
                'unrealized_pl': unrealized_pl,
                'unrealized_pl_pct': unrealized_pl_pct,
                'sector': sector
            })

        # Calculate total P&L
        total_pl = total_value - total_cost
        total_pl_pct = (total_pl / total_cost) * 100 if total_cost > 0 else 0

        # Calculate sector percentages
        for sector in sector_breakdown:
            sector_breakdown[sector] = {
                'value': sector_breakdown[sector],
                'percentage': (sector_breakdown[sector] / total_value) * 100
            }

        return {
            'total_value': total_value,
            'total_cost': total_cost,
            'total_pl': total_pl,
            'total_pl_pct': total_pl_pct,
            'positions': sorted(positions_data, key=lambda x: x['current_value'], reverse=True),
            'sector_breakdown': sector_breakdown
        }

    def analyze_diversification(self, portfolio_value):
        """Analyze portfolio diversification and provide recommendations"""
        if not portfolio_value or not portfolio_value['positions']:
            return None

        sector_breakdown = portfolio_value['sector_breakdown']
        warnings = []
        recommendations = []

        # Check sector concentration
        for sector, data in sector_breakdown.items():
            pct = data['percentage']
            if pct > 60:
                warnings.append(f"❌ {sector}: {pct:.1f}% - HIGHLY CONCENTRATED!")
                recommendations.append(f"Reduce {sector} exposure to below 60%")
            elif pct > 40:
                warnings.append(f"⚠️ {sector}: {pct:.1f}% - High concentration")
                recommendations.append(f"Consider reducing {sector} exposure")

        # Check if any bonds
        has_bonds = 'Bonds' in sector_breakdown
        if not has_bonds:
            recommendations.append("Add bonds (TLT, AGG) for stability and lower volatility")

        # Check if any commodities
        has_commodities = 'Commodities' in sector_breakdown
        if not has_commodities:
            recommendations.append("Add commodities (GLD) as inflation hedge")

        # Check number of positions
        num_positions = len(portfolio_value['positions'])
        if num_positions < 5:
            warnings.append(f"⚠️ Only {num_positions} positions - Low diversification")
            recommendations.append("Consider adding more positions (target: 10-15)")

        # Check for single position dominance
        if num_positions > 1:
            largest_position = portfolio_value['positions'][0]
            largest_pct = (largest_position['current_value'] / portfolio_value['total_value']) * 100
            if largest_pct > 40:
                warnings.append(f"⚠️ {largest_position['symbol']} is {largest_pct:.1f}% of portfolio")
                recommendations.append(f"Consider reducing {largest_position['symbol']} position")

        return {
            'warnings': warnings,
            'recommendations': recommendations,
            'diversification_score': self._calculate_diversification_score(sector_breakdown, num_positions)
        }

    def _calculate_diversification_score(self, sector_breakdown, num_positions):
        """Calculate a diversification score (0-100)"""
        score = 100

        # Penalty for concentration
        for sector, data in sector_breakdown.items():
            pct = data['percentage']
            if pct > 60:
                score -= 30
            elif pct > 40:
                score -= 15
            elif pct > 30:
                score -= 5

        # Penalty for few positions
        if num_positions < 5:
            score -= 20
        elif num_positions < 10:
            score -= 10

        # Bonus for having multiple asset classes
        num_sectors = len(sector_breakdown)
        if num_sectors >= 5:
            score += 10
        elif num_sectors >= 3:
            score += 5

        return max(0, min(100, score))

    def get_position_detail(self, symbol):
        """Get detailed info for a specific position"""
        symbol = symbol.upper()
        if symbol not in self.positions:
            return None

        return {
            'symbol': symbol,
            'position': self.positions[symbol],
            'sector': self.get_sector(symbol)
        }

    def get_trade_history(self):
        """Get all trade history"""
        all_trades = []
        for symbol, position in self.positions.items():
            for trade in position.get('trades', []):
                all_trades.append({
                    'symbol': symbol,
                    **trade
                })

        # Sort by date, most recent first
        all_trades.sort(key=lambda x: x['date'], reverse=True)
        return all_trades


def get_portfolio(chat_id):
    """Get or create portfolio for a chat"""
    return Portfolio(chat_id)