# File: backend/risk_manager.py
"""
RISK MANAGEMENT MODULE
Mengelola risk exposure, position sizing, dan portfolio protection.
"""

from typing import Dict, Optional, List
from dataclasses import dataclass
from datetime import datetime
import json

@dataclass
class RiskLimits:
    """
    Risk limits configuration
    """
    max_position_size_pct: float = 20.0  # Max % dari capital per position
    max_portfolio_drawdown_pct: float = 15.0  # Max portfolio drawdown
    max_daily_loss_pct: float = 5.0  # Max loss per hari
    max_open_positions: int = 5  # Max concurrent positions
    risk_per_trade_pct: float = 2.0  # Risk per trade (untuk position sizing)

class RiskManager:
    """
    Risk management system untuk trading bot
    """
    
    def __init__(self, initial_capital: float, limits: Optional[RiskLimits] = None):
        """
        Args:
            initial_capital: Starting capital
            limits: Risk limits configuration
        """
        self.initial_capital = initial_capital
        self.limits = limits if limits else RiskLimits()
        self.peak_capital = initial_capital
        self.daily_pnl = 0
        self.daily_reset_date = datetime.now().date()
        self.trades_today = 0
        
    def update_daily_tracking(self, current_date):
        """
        Reset daily tracking if new day
        """
        if current_date != self.daily_reset_date:
            self.daily_pnl = 0
            self.trades_today = 0
            self.daily_reset_date = current_date
    
    def calculate_position_size(self, capital: float, entry_price: float, 
                               stop_loss_price: float, risk_pct: Optional[float] = None) -> Dict:
        """
        Calculate optimal position size berdasarkan risk management
        Menggunakan metode "Fixed Fractional Position Sizing"
        
        Args:
            capital: Current available capital
            entry_price: Planned entry price
            stop_loss_price: Stop-loss price
            risk_pct: Risk percentage (override default)
        
        Returns:
            Position sizing recommendation
        """
        risk_per_trade = risk_pct if risk_pct else self.limits.risk_per_trade_pct
        
        # Amount willing to risk
        risk_amount = capital * (risk_per_trade / 100)
        
        # Price difference (risk per unit)
        price_risk = abs(entry_price - stop_loss_price)
        
        if price_risk == 0:
            return {
                'status': 'error',
                'message': 'Stop-loss price cannot equal entry price'
            }
        
        # Calculate position size
        position_size = risk_amount / price_risk
        position_value = position_size * entry_price
        
        # Check against max position size limit
        max_position_value = capital * (self.limits.max_position_size_pct / 100)
        
        if position_value > max_position_value:
            # Reduce to max allowed
            position_size = max_position_value / entry_price
            position_value = max_position_value
            actual_risk = position_size * price_risk
            actual_risk_pct = (actual_risk / capital) * 100
            capped = True
        else:
            actual_risk = risk_amount
            actual_risk_pct = risk_per_trade
            capped = False
        
        position_pct = (position_value / capital) * 100
        
        return {
            'status': 'success',
            'position_size': round(position_size, 8),
            'position_value_usdt': round(position_value, 2),
            'position_pct': round(position_pct, 2),
            'risk_amount': round(actual_risk, 2),
            'risk_pct': round(actual_risk_pct, 2),
            'entry_price': entry_price,
            'stop_loss_price': stop_loss_price,
            'price_risk_per_unit': round(price_risk, 6),
            'capped': capped,
            'message': f"Buy {position_size:.8f} units (${position_value:.2f}) with {actual_risk_pct:.2f}% risk"
        }
    
    def can_open_position(self, current_positions: int, current_capital: float,
                         new_position_value: float) -> Dict:
        """
        Check if new position can be opened based on risk limits
        
        Args:
            current_positions: Number of currently open positions
            current_capital: Current total capital
            new_position_value: Value of new position in USDT
        
        Returns:
            Dictionary with approval status and reasons
        """
        reasons = []
        approved = True
        
        # Check max open positions
        if current_positions >= self.limits.max_open_positions:
            approved = False
            reasons.append(f"Max open positions reached ({self.limits.max_open_positions})")
        
        # Check max position size
        position_pct = (new_position_value / current_capital) * 100
        if position_pct > self.limits.max_position_size_pct:
            approved = False
            reasons.append(f"Position size {position_pct:.1f}% exceeds limit {self.limits.max_position_size_pct}%")
        
        # Check daily loss limit
        self.update_daily_tracking(datetime.now().date())
        daily_loss_pct = (self.daily_pnl / self.initial_capital) * 100
        if daily_loss_pct < -self.limits.max_daily_loss_pct:
            approved = False
            reasons.append(f"Daily loss limit exceeded ({daily_loss_pct:.2f}% < -{self.limits.max_daily_loss_pct}%)")
        
        # Check max drawdown
        current_drawdown = ((self.peak_capital - current_capital) / self.peak_capital) * 100
        if current_drawdown > self.limits.max_portfolio_drawdown_pct:
            approved = False
            reasons.append(f"Portfolio drawdown {current_drawdown:.2f}% exceeds limit {self.limits.max_portfolio_drawdown_pct}%")
        
        return {
            'approved': approved,
            'reasons': reasons if not approved else ['All risk checks passed'],
            'current_positions': current_positions,
            'position_pct': round(position_pct, 2),
            'daily_loss_pct': round(daily_loss_pct, 2),
            'current_drawdown_pct': round(current_drawdown, 2)
        }
    
    def update_peak_capital(self, current_capital: float):
        """
        Update peak capital untuk drawdown calculation
        """
        if current_capital > self.peak_capital:
            self.peak_capital = current_capital
    
    def record_trade_pnl(self, pnl: float):
        """
        Record trade P&L untuk daily tracking
        """
        self.update_daily_tracking(datetime.now().date())
        self.daily_pnl += pnl
        self.trades_today += 1
    
    def calculate_portfolio_risk(self, positions: List[Dict], current_prices: Dict[str, float]) -> Dict:
        """
        Calculate total portfolio risk exposure
        
        Args:
            positions: List of open positions with entry_price and amount
            current_prices: Current market prices
        
        Returns:
            Portfolio risk analysis
        """
        total_position_value = 0
        total_unrealized_pnl = 0
        position_details = []
        
        for pos in positions:
            symbol = pos['symbol']
            amount = pos['amount']
            entry_price = pos['entry_price']
            current_price = current_prices.get(symbol, entry_price)
            
            position_value = amount * current_price
            cost_basis = amount * entry_price
            unrealized_pnl = position_value - cost_basis
            unrealized_pnl_pct = (unrealized_pnl / cost_basis) * 100
            
            total_position_value += position_value
            total_unrealized_pnl += unrealized_pnl
            
            position_details.append({
                'symbol': symbol,
                'position_value': round(position_value, 2),
                'unrealized_pnl': round(unrealized_pnl, 2),
                'unrealized_pnl_pct': round(unrealized_pnl_pct, 2)
            })
        
        return {
            'total_position_value': round(total_position_value, 2),
            'total_unrealized_pnl': round(total_unrealized_pnl, 2),
            'position_count': len(positions),
            'position_details': position_details
        }
    
    def get_risk_summary(self, current_capital: float, open_positions: int) -> Dict:
        """
        Get comprehensive risk summary
        """
        self.update_daily_tracking(datetime.now().date())
        
        current_drawdown = ((self.peak_capital - current_capital) / self.peak_capital) * 100
        daily_loss_pct = (self.daily_pnl / self.initial_capital) * 100
        
        # Calculate remaining limits
        remaining_drawdown = self.limits.max_portfolio_drawdown_pct - current_drawdown
        remaining_daily_loss = self.limits.max_daily_loss_pct + daily_loss_pct
        remaining_positions = self.limits.max_open_positions - open_positions
        
        # Risk status
        risk_level = 'LOW'
        if current_drawdown > self.limits.max_portfolio_drawdown_pct * 0.7:
            risk_level = 'HIGH'
        elif current_drawdown > self.limits.max_portfolio_drawdown_pct * 0.4:
            risk_level = 'MEDIUM'
        
        return {
            'risk_level': risk_level,
            'current_capital': round(current_capital, 2),
            'peak_capital': round(self.peak_capital, 2),
            'current_drawdown_pct': round(current_drawdown, 2),
            'remaining_drawdown_pct': round(remaining_drawdown, 2),
            'daily_pnl': round(self.daily_pnl, 2),
            'daily_loss_pct': round(daily_loss_pct, 2),
            'remaining_daily_loss_pct': round(remaining_daily_loss, 2),
            'open_positions': open_positions,
            'remaining_positions': remaining_positions,
            'trades_today': self.trades_today,
            'limits': {
                'max_position_size_pct': self.limits.max_position_size_pct,
                'max_drawdown_pct': self.limits.max_portfolio_drawdown_pct,
                'max_daily_loss_pct': self.limits.max_daily_loss_pct,
                'max_positions': self.limits.max_open_positions,
                'risk_per_trade_pct': self.limits.risk_per_trade_pct
            }
        }
    
    def calculate_kelly_criterion(self, win_rate: float, avg_win: float, avg_loss: float) -> Dict:
        """
        Calculate optimal position size using Kelly Criterion
        
        Kelly % = W - [(1 - W) / R]
        Where:
            W = Win rate (decimal)
            R = Win/Loss ratio
        
        Args:
            win_rate: Win rate in percentage (e.g., 60 for 60%)
            avg_win: Average winning amount
            avg_loss: Average losing amount (positive number)
        
        Returns:
            Kelly calculation result
        """
        if avg_loss == 0 or win_rate == 0:
            return {
                'status': 'error',
                'message': 'Invalid input: avg_loss and win_rate must be > 0'
            }
        
        w = win_rate / 100  # Convert to decimal
        r = abs(avg_win / avg_loss)  # Win/Loss ratio
        
        kelly_pct = (w - ((1 - w) / r)) * 100
        
        # Half Kelly (more conservative)
        half_kelly_pct = kelly_pct / 2
        
        # Quarter Kelly (very conservative)
        quarter_kelly_pct = kelly_pct / 4
        
        recommendation = "FULL KELLY"
        if kelly_pct < 0:
            recommendation = "DO NOT TRADE (Negative edge)"
        elif kelly_pct > 25:
            recommendation = "USE HALF or QUARTER KELLY (Too aggressive)"
        
        return {
            'status': 'success',
            'kelly_pct': round(kelly_pct, 2),
            'half_kelly_pct': round(half_kelly_pct, 2),
            'quarter_kelly_pct': round(quarter_kelly_pct, 2),
            'win_rate': win_rate,
            'win_loss_ratio': round(r, 2),
            'recommendation': recommendation,
            'message': f"Optimal position size: {kelly_pct:.2f}% (Kelly), {half_kelly_pct:.2f}% (Half Kelly)"
        }
    
    def adjust_for_volatility(self, base_position_size: float, current_volatility: float,
                             avg_volatility: float) -> Dict:
        """
        Adjust position size based on market volatility
        High volatility = Reduce position size
        Low volatility = Can increase slightly
        
        Args:
            base_position_size: Base position size in USDT
            current_volatility: Current market volatility (e.g., ATR, StdDev)
            avg_volatility: Average/normal volatility
        
        Returns:
            Adjusted position size
        """
        if avg_volatility == 0:
            return {
                'status': 'error',
                'message': 'Average volatility cannot be 0'
            }
        
        volatility_ratio = current_volatility / avg_volatility
        
        # Adjustment factor: inverse of volatility ratio
        # If volatility is 2x normal, reduce position to 0.5x
        adjustment_factor = 1 / volatility_ratio
        
        # Cap adjustment between 0.5x and 1.5x
        adjustment_factor = max(0.5, min(1.5, adjustment_factor))
        
        adjusted_size = base_position_size * adjustment_factor
        
        volatility_status = "NORMAL"
        if volatility_ratio > 1.5:
            volatility_status = "HIGH (Reduce size)"
        elif volatility_ratio < 0.7:
            volatility_status = "LOW (Can increase size)"
        
        return {
            'status': 'success',
            'base_size': round(base_position_size, 2),
            'adjusted_size': round(adjusted_size, 2),
            'adjustment_factor': round(adjustment_factor, 2),
            'volatility_ratio': round(volatility_ratio, 2),
            'volatility_status': volatility_status,
            'message': f"Position adjusted from ${base_position_size:.2f} to ${adjusted_size:.2f} due to {volatility_status.lower()} volatility"
        }

# Example usage
if __name__ == "__main__":
    # Initialize risk manager
    rm = RiskManager(initial_capital=1000.0)
    
    print("=" * 60)
    print("RISK MANAGER DEMO")
    print("=" * 60)
    
    # Example 1: Position sizing
    print("\n1. POSITION SIZING")
    ps = rm.calculate_position_size(
        capital=1000,
        entry_price=50000,
        stop_loss_price=48500  # 3% stop-loss
    )
    print(f"   {ps['message']}")
    print(f"   Position: {ps['position_size']} BTC (${ps['position_value_usdt']})")
    print(f"   Risk: ${ps['risk_amount']} ({ps['risk_pct']}%)")
    
    # Example 2: Can open position?
    print("\n2. CHECK IF CAN OPEN NEW POSITION")
    check = rm.can_open_position(
        current_positions=2,
        current_capital=1000,
        new_position_value=150
    )
    print(f"   Approved: {check['approved']}")
    print(f"   Reasons: {', '.join(check['reasons'])}")
    
    # Example 3: Kelly Criterion
    print("\n3. KELLY CRITERION")
    kelly = rm.calculate_kelly_criterion(
        win_rate=55,
        avg_win=50,
        avg_loss=30
    )
    print(f"   {kelly['message']}")
    print(f"   Recommendation: {kelly['recommendation']}")
    
    # Example 4: Risk summary
    print("\n4. RISK SUMMARY")
    summary = rm.get_risk_summary(current_capital=950, open_positions=3)
    print(f"   Risk Level: {summary['risk_level']}")
    print(f"   Drawdown: {summary['current_drawdown_pct']:.2f}%")
    print(f"   Open Positions: {summary['open_positions']}/{summary['limits']['max_positions']}")
    
    print("\n" + "=" * 60)
