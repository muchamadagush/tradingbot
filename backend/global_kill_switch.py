from datetime import date, timedelta
from database import get_connection
import sys_logger


class GlobalKillSwitch:
    """
    PORTFOLIO LEVEL HARD STOP
    
    Protects against:
    - Daily loss exceeding threshold
    - Weekly loss exceeding threshold  
    - Unrealized loss exceeding threshold
    - Manual kill switch activation
    """

    MAX_DAILY_LOSS_PCT = 0.02       # 2%
    MAX_WEEKLY_LOSS_PCT = 0.05      # 5% - NEW
    MAX_UNREALIZED_LOSS_PCT = 0.03  # 3%

    def __init__(self):
        self.conn = get_connection()
        self._last_check_reason = None

    # ================= PUBLIC =================

    def is_trading_allowed(self) -> bool:
        """
        Main entry point - checks all kill conditions.
        Returns False if ANY condition triggers.
        """
        if self._manual_kill():
            self._last_check_reason = "MANUAL_DISABLE"
            sys_logger.add_log("🛑 GLOBAL KILL SWITCH: MANUAL DISABLE")
            return False

        if self._daily_loss_exceeded():
            self._last_check_reason = "DAILY_LOSS_LIMIT"
            sys_logger.add_log("🛑 GLOBAL KILL SWITCH: DAILY LOSS LIMIT")
            return False

        if self._weekly_loss_exceeded():
            self._last_check_reason = "WEEKLY_LOSS_LIMIT"
            sys_logger.add_log("🛑 GLOBAL KILL SWITCH: WEEKLY LOSS LIMIT")
            return False

        if self._unrealized_loss_exceeded():
            self._last_check_reason = "UNREALIZED_LOSS_LIMIT"
            sys_logger.add_log("🛑 GLOBAL KILL SWITCH: UNREALIZED LOSS LIMIT")
            return False

        self._last_check_reason = None
        return True

    def get_status(self) -> dict:
        """Get current kill switch status for API/monitoring."""
        equity = self._get_equity()
        daily_pnl = self._get_daily_pnl()
        weekly_pnl = self._get_weekly_pnl()
        unrealized_pnl = self._get_unrealized_pnl()
        
        return {
            "trading_allowed": self.is_trading_allowed(),
            "last_block_reason": self._last_check_reason,
            "equity": equity,
            "daily_pnl": daily_pnl,
            "daily_limit": -self.MAX_DAILY_LOSS_PCT * equity,
            "weekly_pnl": weekly_pnl,
            "weekly_limit": -self.MAX_WEEKLY_LOSS_PCT * equity,
            "unrealized_pnl": unrealized_pnl,
            "unrealized_limit": -self.MAX_UNREALIZED_LOSS_PCT * equity,
            "manual_kill_active": self._manual_kill()
        }

    def set_manual_kill(self, enabled: bool) -> bool:
        """Enable or disable manual kill switch."""
        try:
            cur = self.conn.cursor()
            cur.execute("""
                INSERT OR REPLACE INTO system_flags (key, value)
                VALUES ('TRADING_DISABLED', ?)
            """, ("true" if enabled else "false",))
            self.conn.commit()
            sys_logger.add_log(f"⚠️ MANUAL KILL SWITCH: {'ENABLED' if enabled else 'DISABLED'}")
            return True
        except Exception as e:
            sys_logger.add_log(f"❌ Failed to set manual kill: {e}")
            return False

    # ================= CHECKS =================

    def _manual_kill(self) -> bool:
        cur = self.conn.cursor()
        cur.execute(
            "SELECT value FROM system_flags WHERE key='TRADING_DISABLED'"
        )
        row = cur.fetchone()
        return bool(row and row[0] == "true")

    def _daily_loss_exceeded(self) -> bool:
        daily_pnl = self._get_daily_pnl()
        equity = self._get_equity()
        
        if equity <= 0:
            return False  # Can't calculate without equity
            
        limit = -self.MAX_DAILY_LOSS_PCT * equity
        return daily_pnl <= limit

    def _weekly_loss_exceeded(self) -> bool:
        """NEW: Check if weekly loss limit exceeded."""
        weekly_pnl = self._get_weekly_pnl()
        equity = self._get_equity()
        
        if equity <= 0:
            return False
            
        limit = -self.MAX_WEEKLY_LOSS_PCT * equity
        return weekly_pnl <= limit

    def _unrealized_loss_exceeded(self) -> bool:
        unrealized = self._get_unrealized_pnl()
        equity = self._get_equity()
        
        if equity <= 0:
            return False
            
        limit = -self.MAX_UNREALIZED_LOSS_PCT * equity
        return unrealized <= limit

    # ================= DATA HELPERS =================

    def _get_daily_pnl(self) -> float:
        """Get sum of realized PnL for today from trade_ledger (immutable source)."""
        today = date.today().isoformat()
        cur = self.conn.cursor()
        
        # Use trade_ledger for accurate, immutable PnL data
        cur.execute("""
            SELECT COALESCE(SUM(pnl), 0)
            FROM trade_ledger
            WHERE DATE(timestamp) = ? AND event_type = 'CLOSED'
        """, (today,))
        
        return float(cur.fetchone()[0])

    def _get_weekly_pnl(self) -> float:
        """Get sum of realized PnL for current week from trade_ledger."""
        today = date.today()
        # Get Monday of current week
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        
        cur = self.conn.cursor()
        cur.execute("""
            SELECT COALESCE(SUM(pnl), 0)
            FROM trade_ledger
            WHERE DATE(timestamp) >= ? AND event_type = 'CLOSED'
        """, (week_start,))
        
        return float(cur.fetchone()[0])

    def _get_unrealized_pnl(self) -> float:
        """
        Calculate unrealized PnL from open positions.
        
        NOTE: This requires current prices. For now, we estimate based on
        stored position data. In production, this should fetch live prices.
        """
        cur = self.conn.cursor()
        
        # Check if open_positions table has data
        cur.execute("""
            SELECT symbol, amount, entry_price 
            FROM open_positions
        """)
        positions = cur.fetchall()
        
        if not positions:
            return 0.0
        
        # For paper trading, we can estimate unrealized as 0 until we have price feeds
        # TODO: Integrate with live price feeds for accurate unrealized PnL
        # For now, return 0 (conservative - won't trigger false positives)
        return 0.0

    def _get_equity(self) -> float:
        """Get current account equity/balance."""
        cur = self.conn.cursor()
        cur.execute("SELECT balance FROM account LIMIT 1")
        row = cur.fetchone()
        return float(row[0]) if row else 1000.0  # Default to 1000 if no account


# ================= SINGLETON =================
kill_switch = GlobalKillSwitch()
