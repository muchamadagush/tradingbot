"""
Database adapter for PostgreSQL migration.

This module provides backward-compatible functions from the old SQLite database.py
while using PostgreSQL under the hood via database_pg.py.

Allows gradual migration without rewriting all of main.py at once.
"""

from datetime import datetime
from typing import Optional, List, Dict, Any
import json
from enum import Enum

# Import from new PostgreSQL layer
from database_pg import (
    get_db_session, session_scope, Trade, TradeLedger, Account, 
    OpenPosition, SystemFlag, BacktestResult, TradeState, BotType,
    get_account_balance as pg_get_account_balance,
    update_account_balance as pg_update_account_balance,
    get_system_flag as pg_get_system_flag,
    set_system_flag as pg_set_system_flag
)

# ===== BACKWARD COMPATIBILITY WRAPPER =====

def get_connection():
    """
    DEPRECATED: Use get_db_session() instead.
    This wrapper returns a session-like object for backward compatibility.
    """
    return get_db_session()


def transaction():
    """
    DEPRECATED: Use session_scope() instead.
    Wrapper for backward compatibility.
    """
    return session_scope()


def init_db():
    """
    DEPRECATED: Use init_pg_db() instead.
    """
    from database_pg import init_pg_db
    init_pg_db()


# ===== TRADE OPERATIONS =====

def save_trade(
    symbol: str,
    side: str,
    buy_price: float,
    amount: float,
    total_usdt: float,
    mode: str = "PAPER",
    bot_type: str = "HUNTER"
) -> int:
    """Save new trade to database."""
    with session_scope() as session:
        trade = Trade(
            symbol=symbol,
            side=side,
            buy_price=buy_price,
            amount=amount,
            total_usdt=total_usdt,
            status=TradeState.PENDING,
            mode=mode,
            bot_type=bot_type,
            created_at=datetime.utcnow()
        )
        session.add(trade)
        session.flush()
        trade_id = trade.id
    return trade_id


def get_trades(limit: int = 100) -> List[Dict]:
    """Get recent trades."""
    session = get_db_session()
    try:
        trades = session.query(Trade).order_by(Trade.created_at.desc()).limit(limit).all()
        return [
            {
                'id': t.id,
                'symbol': t.symbol,
                'side': t.side,
                'buy_price': t.buy_price,
                'amount': t.amount,
                'total_usdt': t.total_usdt,
                'status': t.status,
                'sell_price': t.sell_price,
                'profit_usdt': t.profit_usdt,
                'fee_paid': t.fee_paid,
                'mode': t.mode,
                'bot_type': t.bot_type,
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'opened_at': t.opened_at.isoformat() if t.opened_at else None,
                'closing_at': t.closing_at.isoformat() if t.closing_at else None,
                'closed_at': t.closed_at.isoformat() if t.closed_at else None,
            }
            for t in trades
        ]
    finally:
        session.close()


def get_open_trades(symbol: Optional[str] = None) -> List[Dict]:
    """Get open trades, optionally filtered by symbol."""
    session = get_db_session()
    try:
        query = session.query(Trade).filter(Trade.status == TradeState.OPEN)
        if symbol:
            query = query.filter(Trade.symbol == symbol)
        trades = query.all()
        return [
            {
                'id': t.id,
                'symbol': t.symbol,
                'amount': t.amount,
                'buy_price': t.buy_price,
                'status': t.status,
                'opened_at': t.opened_at.isoformat() if t.opened_at else None,
            }
            for t in trades
        ]
    finally:
        session.close()


def close_trade(
    trade_id: int,
    sell_price: float,
    reason: str = "MANUAL"
) -> bool:
    """Close a trade (update status to CLOSING then CLOSED)."""
    with session_scope() as session:
        trade = session.query(Trade).filter_by(id=trade_id).first()
        if not trade:
            return False
        
        # Update trade
        trade.status = TradeState.CLOSING
        trade.closing_at = datetime.utcnow()
        trade.sell_price = sell_price
        trade.profit_usdt = (sell_price - trade.buy_price) * trade.amount
        
        # Log to ledger
        ledger = TradeLedger(
            trade_id=trade_id,
            event_type="CLOSING",
            old_state=TradeState.OPEN,
            new_state=TradeState.CLOSING,
            price=sell_price,
            reason=reason,
            timestamp=datetime.utcnow()
        )
        session.add(ledger)
    
    return True


def open_trade(trade_id: int) -> bool:
    """Mark trade as OPEN (from PENDING)."""
    with session_scope() as session:
        trade = session.query(Trade).filter_by(id=trade_id).first()
        if not trade:
            return False
        
        trade.status = TradeState.OPEN
        trade.opened_at = datetime.utcnow()
        
        ledger = TradeLedger(
            trade_id=trade_id,
            event_type="OPENED",
            old_state=TradeState.PENDING,
            new_state=TradeState.OPEN,
            price=trade.buy_price,
            reason="ORDER_CONFIRMED",
            timestamp=datetime.utcnow()
        )
        session.add(ledger)
    
    return True


def get_trade(trade_id: int) -> Optional[Dict]:
    """Get trade by ID."""
    session = get_db_session()
    try:
        trade = session.query(Trade).filter_by(id=trade_id).first()
        if not trade:
            return None
        
        return {
            'id': trade.id,
            'symbol': trade.symbol,
            'side': trade.side,
            'buy_price': trade.buy_price,
            'amount': trade.amount,
            'total_usdt': trade.total_usdt,
            'status': trade.status,
            'sell_price': trade.sell_price,
            'profit_usdt': trade.profit_usdt,
            'fee_paid': trade.fee_paid,
            'mode': trade.mode,
            'bot_type': trade.bot_type,
            'created_at': trade.created_at.isoformat() if trade.created_at else None,
        }
    finally:
        session.close()


# ===== ACCOUNT OPERATIONS =====

def get_account_balance() -> float:
    """Get current account balance."""
    return pg_get_account_balance()


def update_account_balance(balance: float):
    """Update account balance."""
    pg_update_account_balance(balance)


def get_account() -> Dict:
    """Get full account information."""
    with session_scope() as session:
        account = session.query(Account).filter_by(id=1).first()
        if not account:
            return {'id': 1, 'balance': 0.0}
        
        return {
            'id': account.id,
            'balance': account.balance,
            'updated_at': account.updated_at.isoformat() if account.updated_at else None,
        }


# ===== SYSTEM FLAGS (P0: Kill Switch) =====

def get_system_flag(key: str, default: str = None) -> Optional[str]:
    """Get system flag value."""
    value = pg_get_system_flag(key)
    return value if value else default


def set_system_flag(key: str, value: str):
    """Set system flag value."""
    pg_set_system_flag(key, value)


def is_trading_disabled() -> bool:
    """Check if global kill switch is active."""
    value = get_system_flag('TRADING_DISABLED', 'false')
    return value.lower() == 'true'


def set_trading_disabled(disabled: bool):
    """Enable/disable global kill switch."""
    set_system_flag('TRADING_DISABLED', 'true' if disabled else 'false')


# ===== OPEN POSITIONS =====

def save_open_position(
    symbol: str,
    amount: float,
    entry_price: float,
    current_price: float,
    bot_type: str = "HUNTER"
) -> int:
    """Save open position."""
    with session_scope() as session:
        position = OpenPosition(
            symbol=symbol,
            amount=amount,
            entry_price=entry_price,
            current_price=current_price,
            unrealized_pnl=(current_price - entry_price) * amount,
            bot_type=bot_type
        )
        session.add(position)
        session.flush()
        position_id = position.id
    return position_id


def get_open_positions() -> List[Dict]:
    """Get all open positions."""
    session = get_db_session()
    try:
        positions = session.query(OpenPosition).all()
        return [
            {
                'id': p.id,
                'symbol': p.symbol,
                'amount': p.amount,
                'entry_price': p.entry_price,
                'current_price': p.current_price,
                'unrealized_pnl': p.unrealized_pnl,
                'bot_type': p.bot_type,
                'opened_at': p.opened_at.isoformat() if p.opened_at else None,
            }
            for p in positions
        ]
    finally:
        session.close()


def delete_open_position(position_id: int) -> bool:
    """Delete open position."""
    with session_scope() as session:
        position = session.query(OpenPosition).filter_by(id=position_id).first()
        if position:
            session.delete(position)
            return True
    return False


# ===== BACKTEST RESULTS =====

def save_backtest_result(result: Dict) -> int:
    """Save backtest result."""
    with session_scope() as session:
        backtest = BacktestResult(
            symbol=result['symbol'],
            timeframe=result['timeframe'],
            period_days=result['period_days'],
            initial_capital=result['initial_capital'],
            final_capital=result['final_capital'],
            roi_pct=result['roi_pct'],
            total_trades=result['total_trades'],
            win_rate_pct=result['win_rate_pct'],
            max_drawdown_pct=result['max_drawdown_pct'],
            profit_factor=result['profit_factor'],
            total_fees_paid=result['total_fees_paid'],
            result_json=json.dumps(result, default=str)
        )
        session.add(backtest)
        session.flush()
        backtest_id = backtest.id
    return backtest_id


def get_backtest_history(limit: int = 10) -> List[Dict]:
    """Get backtest history."""
    session = get_db_session()
    try:
        results = session.query(BacktestResult).order_by(BacktestResult.created_at.desc()).limit(limit).all()
        return [
            {
                'id': r.id,
                'symbol': r.symbol,
                'timeframe': r.timeframe,
                'period_days': r.period_days,
                'initial_capital': r.initial_capital,
                'final_capital': r.final_capital,
                'roi_pct': r.roi_pct,
                'total_trades': r.total_trades,
                'win_rate_pct': r.win_rate_pct,
                'max_drawdown_pct': r.max_drawdown_pct,
                'profit_factor': r.profit_factor,
                'total_fees_paid': r.total_fees_paid,
                'created_at': r.created_at.isoformat() if r.created_at else None,
            }
            for r in results
        ]
    finally:
        session.close()


# ===== TRADE LEDGER (P1: Immutable Audit Log) =====

def get_trade_ledger(trade_id: int) -> List[Dict]:
    """Get ledger entries for a trade."""
    session = get_db_session()
    try:
        entries = session.query(TradeLedger).filter_by(trade_id=trade_id).order_by(TradeLedger.timestamp).all()
        return [
            {
                'id': e.id,
                'trade_id': e.trade_id,
                'event_type': e.event_type,
                'old_state': e.old_state,
                'new_state': e.new_state,
                'price': e.price,
                'amount': e.amount,
                'value_usdt': e.value_usdt,
                'fee': e.fee,
                'pnl': e.pnl,
                'reason': e.reason,
                'timestamp': e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in entries
        ]
    finally:
        session.close()


def get_trade_history(limit: int = 50) -> List[Dict]:
    """
    Get recent trades from database.
    Used by /api/trade/history endpoint.
    """
    session = get_db_session()
    try:
        trades = session.query(Trade).order_by(Trade.id.desc()).limit(limit).all()
        return [
            {
                'id': t.id,
                'symbol': t.symbol,
                'side': t.side,
                'buy_price': t.buy_price,
                'sell_price': t.sell_price,
                'amount': t.amount,
                'total_usdt': t.total_usdt,
                'status': t.status,
                'entry_time': t.created_at.isoformat() if t.created_at else None,
                'exit_time': t.updated_at.isoformat() if t.updated_at else None,
                'bot_type': t.bot_type,
                'mode': t.mode,
            }
            for t in trades
        ]
    finally:
        session.close()


if __name__ == "__main__":
    # Test the adapter
    print("✅ Database adapter initialized")
