import sqlite3
from datetime import datetime
from contextlib import contextmanager
from typing import Optional, Dict, List
from enum import Enum
import json


DB_NAME = "crypto_bot.db"


# =========================
# TRADE STATE MACHINE (P1)
# =========================
class TradeState(str, Enum):
    PENDING = "PENDING"     # Order submitted, not yet confirmed
    OPEN = "OPEN"           # Position is active
    CLOSING = "CLOSING"     # Sell order submitted
    CLOSED = "CLOSED"       # Position fully closed
    CANCELLED = "CANCELLED" # Order cancelled
    FAILED = "FAILED"       # Order failed


class BotType(str, Enum):
    HUNTER = "HUNTER"
    TRADER = "TRADER"
    SNIPER = "SNIPER"


# =========================
# CONNECTION
# =========================
def get_connection():
    conn = sqlite3.connect(DB_NAME, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


@contextmanager
def transaction():
    """
    Context manager for atomic database transactions.
    Usage:
        with transaction() as conn:
            cursor = conn.cursor()
            cursor.execute(...)
            # Auto-commit on success, rollback on exception
    """
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# =========================
# INIT DATABASE
# =========================
def init_db():
    conn = get_connection()
    cursor = conn.cursor()

    # -------------------------------------------------
    # 1. TABEL TRADES (UPDATED WITH STATE MACHINE)
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,          -- 'BUY'
            buy_price REAL NOT NULL,
            amount REAL NOT NULL,
            total_usdt REAL NOT NULL,

            status TEXT DEFAULT 'PENDING',  -- PENDING/OPEN/CLOSING/CLOSED/CANCELLED/FAILED
            sell_price REAL,
            profit_usdt REAL,

            fee_paid REAL DEFAULT 0,
            mode TEXT DEFAULT 'LIVE',    -- LIVE / PAPER / BACKTEST
            bot_type TEXT DEFAULT 'HUNTER',  -- HUNTER / TRADER / SNIPER

            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            opened_at DATETIME,          -- When PENDING -> OPEN
            closing_at DATETIME,         -- When OPEN -> CLOSING
            closed_at DATETIME           -- When CLOSING -> CLOSED
        )
    """)

    # -------------------------------------------------
    # 1b. TRADE LEDGER (IMMUTABLE AUDIT LOG) - NEW P1
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS trade_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_id INTEGER NOT NULL,
            event_type TEXT NOT NULL,    -- CREATED/OPENED/CLOSING/CLOSED/CANCELLED/FAILED
            old_state TEXT,
            new_state TEXT NOT NULL,
            
            -- Snapshot data at this moment
            price REAL,
            amount REAL,
            value_usdt REAL,
            fee REAL DEFAULT 0,
            pnl REAL,
            
            -- Metadata
            bot_type TEXT,
            reason TEXT,                 -- Why state changed (TP_HIT, SL_HIT, MANUAL, ERROR)
            
            -- Immutable timestamp
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            
            FOREIGN KEY (trade_id) REFERENCES trades(id)
        )
    """)
    
    # Create index for fast lookups
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_trade_id ON trade_ledger(trade_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_timestamp ON trade_ledger(timestamp)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_ledger_bot_type ON trade_ledger(bot_type)
    """)

    # -------------------------------------------------
    # 2. BACKTEST RESULTS (EXISTING)
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS backtest_results (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            timeframe TEXT NOT NULL,
            period_days INTEGER NOT NULL,
            initial_capital REAL NOT NULL,
            final_capital REAL NOT NULL,
            roi_pct REAL NOT NULL,
            total_trades INTEGER NOT NULL,
            win_rate_pct REAL NOT NULL,
            max_drawdown_pct REAL NOT NULL,
            profit_factor REAL NOT NULL,
            total_fees_paid REAL NOT NULL,
            result_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # -------------------------------------------------
    # 3. PAPER TRADING SNAPSHOTS (EXISTING)
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS paper_trading_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            balance REAL NOT NULL,
            total_equity REAL NOT NULL,
            total_pnl REAL NOT NULL,
            open_positions INTEGER NOT NULL,
            snapshot_json TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =================================================
    # 🔴 P0.1 ADDITIONS (WAJIB UNTUK GLOBAL KILL SWITCH)
    # =================================================

    # -------------------------------------------------
    # 4. SYSTEM FLAGS (MANUAL KILL SWITCH)
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_flags (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO system_flags (key, value)
        VALUES ('TRADING_DISABLED', 'false')
    """)

    # -------------------------------------------------
    # 5. ACCOUNT (EQUITY SOURCE)
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS account (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            balance REAL NOT NULL,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cursor.execute("""
        INSERT OR IGNORE INTO account (id, balance)
        VALUES (1, 0)
    """)

    # -------------------------------------------------
    # 6. OPEN POSITIONS (UNREALIZED PnL)
    # -------------------------------------------------
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS open_positions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            amount REAL NOT NULL,
            entry_price REAL NOT NULL,
            current_price REAL NOT NULL,
            unrealized_pnl REAL NOT NULL,
            bot_type TEXT,              -- HUNTER / TRADER / SNIPPER
            opened_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print("✅ Database initialized (SAFE + KILL SWITCH READY)")


# =========================
# BACKTEST HELPERS
# =========================
def save_backtest_result(result: dict):
    conn = get_connection()
    cursor = conn.cursor()
    import json

    cursor.execute("""
        INSERT INTO backtest_results (
            symbol, timeframe, period_days,
            initial_capital, final_capital, roi_pct,
            total_trades, win_rate_pct, max_drawdown_pct,
            profit_factor, total_fees_paid, result_json
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        result["symbol"],
        result["timeframe"],
        result["period_days"],
        result["initial_capital"],
        result["final_capital"],
        result["roi_pct"],
        result["total_trades"],
        result["win_rate_pct"],
        result["max_drawdown_pct"],
        result["profit_factor"],
        result["total_fees_paid"],
        json.dumps(result, default=str)
    ))

    conn.commit()
    backtest_id = cursor.lastrowid
    conn.close()
    return backtest_id


def get_backtest_history(limit=10):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT *
        FROM backtest_results
        ORDER BY created_at DESC
        LIMIT ?
    """, (limit,))

    rows = cursor.fetchall()
    conn.close()
    return rows


# =========================
# ACCOUNT / EQUITY HELPERS
# =========================
def update_account_balance(balance: float):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE account
        SET balance = ?, updated_at = ?
        WHERE id = 1
    """, (balance, datetime.utcnow()))

    conn.commit()
    conn.close()


def get_account_balance() -> float:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT balance FROM account WHERE id = 1")
    row = cursor.fetchone()
    conn.close()
    return float(row["balance"]) if row else 0.0


# =========================
# SYSTEM FLAG HELPERS
# =========================
def set_trading_disabled(value: bool):
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE system_flags
        SET value = ?
        WHERE key = 'TRADING_DISABLED'
    """, ("true" if value else "false",))

    conn.commit()
    conn.close()


def is_trading_disabled() -> bool:
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT value FROM system_flags
        WHERE key = 'TRADING_DISABLED'
    """)
    row = cursor.fetchone()
    conn.close()
    return bool(row and row["value"] == "true")


# =========================================================
# ATOMIC TRADE LIFECYCLE (P1)
# =========================================================

def create_trade(
    symbol: str,
    buy_price: float,
    amount: float,
    total_usdt: float,
    bot_type: str = "HUNTER",
    mode: str = "PAPER",
    fee: float = 0.0
) -> int:
    """
    Create a new trade in PENDING state.
    Returns trade_id.
    """
    with transaction() as conn:
        cursor = conn.cursor()
        now = datetime.utcnow()
        
        # Insert trade in PENDING state
        cursor.execute("""
            INSERT INTO trades (
                symbol, side, buy_price, amount, total_usdt,
                status, fee_paid, mode, bot_type, created_at
            ) VALUES (?, 'BUY', ?, ?, ?, 'PENDING', ?, ?, ?, ?)
        """, (symbol, buy_price, amount, total_usdt, fee, mode, bot_type, now))
        
        trade_id = cursor.lastrowid
        
        # Log to immutable ledger
        cursor.execute("""
            INSERT INTO trade_ledger (
                trade_id, event_type, old_state, new_state,
                price, amount, value_usdt, fee, bot_type, reason, timestamp
            ) VALUES (?, 'CREATED', NULL, 'PENDING', ?, ?, ?, ?, ?, 'NEW_ORDER', ?)
        """, (trade_id, buy_price, amount, total_usdt, fee, bot_type, now))
        
        return trade_id


def open_trade(trade_id: int, reason: str = "ORDER_FILLED") -> bool:
    """
    Transition trade from PENDING -> OPEN.
    Called when buy order is confirmed.
    """
    with transaction() as conn:
        cursor = conn.cursor()
        now = datetime.utcnow()
        
        # Verify current state
        cursor.execute("SELECT status, symbol, buy_price, amount, total_usdt, bot_type FROM trades WHERE id = ?", (trade_id,))
        trade = cursor.fetchone()
        
        if not trade or trade["status"] != "PENDING":
            return False
        
        # Update state
        cursor.execute("""
            UPDATE trades SET status = 'OPEN', opened_at = ? WHERE id = ?
        """, (now, trade_id))
        
        # Log to ledger
        cursor.execute("""
            INSERT INTO trade_ledger (
                trade_id, event_type, old_state, new_state,
                price, amount, value_usdt, bot_type, reason, timestamp
            ) VALUES (?, 'OPENED', 'PENDING', 'OPEN', ?, ?, ?, ?, ?, ?)
        """, (trade_id, trade["buy_price"], trade["amount"], trade["total_usdt"], trade["bot_type"], reason, now))
        
        return True


def start_closing_trade(trade_id: int, reason: str = "SELL_ORDER") -> bool:
    """
    Transition trade from OPEN -> CLOSING.
    Called when sell order is submitted.
    """
    with transaction() as conn:
        cursor = conn.cursor()
        now = datetime.utcnow()
        
        cursor.execute("SELECT status, bot_type FROM trades WHERE id = ?", (trade_id,))
        trade = cursor.fetchone()
        
        if not trade or trade["status"] != "OPEN":
            return False
        
        cursor.execute("""
            UPDATE trades SET status = 'CLOSING', closing_at = ? WHERE id = ?
        """, (now, trade_id))
        
        cursor.execute("""
            INSERT INTO trade_ledger (
                trade_id, event_type, old_state, new_state,
                bot_type, reason, timestamp
            ) VALUES (?, 'CLOSING', 'OPEN', 'CLOSING', ?, ?, ?)
        """, (trade_id, trade["bot_type"], reason, now))
        
        return True


def close_trade(
    trade_id: int,
    sell_price: float,
    profit: float,
    fee: float = 0.0,
    reason: str = "TP_HIT"
) -> bool:
    """
    Transition trade from CLOSING -> CLOSED.
    Called when sell order is confirmed.
    """
    with transaction() as conn:
        cursor = conn.cursor()
        now = datetime.utcnow()
        
        cursor.execute("SELECT status, buy_price, amount, fee_paid, bot_type FROM trades WHERE id = ?", (trade_id,))
        trade = cursor.fetchone()
        
        if not trade or trade["status"] not in ("OPEN", "CLOSING"):
            return False
        
        old_state = trade["status"]
        total_fee = trade["fee_paid"] + fee
        
        cursor.execute("""
            UPDATE trades 
            SET status = 'CLOSED', sell_price = ?, profit_usdt = ?, 
                fee_paid = ?, closed_at = ?
            WHERE id = ?
        """, (sell_price, profit, total_fee, now, trade_id))
        
        cursor.execute("""
            INSERT INTO trade_ledger (
                trade_id, event_type, old_state, new_state,
                price, amount, value_usdt, fee, pnl, bot_type, reason, timestamp
            ) VALUES (?, 'CLOSED', ?, 'CLOSED', ?, ?, ?, ?, ?, ?, ?, ?)
        """, (trade_id, old_state, sell_price, trade["amount"], 
              sell_price * trade["amount"], fee, profit, trade["bot_type"], reason, now))
        
        return True


def cancel_trade(trade_id: int, reason: str = "USER_CANCEL") -> bool:
    """
    Cancel a trade (only if PENDING or OPEN).
    """
    with transaction() as conn:
        cursor = conn.cursor()
        now = datetime.utcnow()
        
        cursor.execute("SELECT status, bot_type FROM trades WHERE id = ?", (trade_id,))
        trade = cursor.fetchone()
        
        if not trade or trade["status"] not in ("PENDING", "OPEN"):
            return False
        
        old_state = trade["status"]
        
        cursor.execute("""
            UPDATE trades SET status = 'CANCELLED', closed_at = ? WHERE id = ?
        """, (now, trade_id))
        
        cursor.execute("""
            INSERT INTO trade_ledger (
                trade_id, event_type, old_state, new_state,
                bot_type, reason, timestamp
            ) VALUES (?, 'CANCELLED', ?, 'CANCELLED', ?, ?, ?)
        """, (trade_id, old_state, trade["bot_type"], reason, now))
        
        return True


def fail_trade(trade_id: int, reason: str = "ORDER_FAILED") -> bool:
    """
    Mark trade as failed.
    """
    with transaction() as conn:
        cursor = conn.cursor()
        now = datetime.utcnow()
        
        cursor.execute("SELECT status, bot_type FROM trades WHERE id = ?", (trade_id,))
        trade = cursor.fetchone()
        
        if not trade:
            return False
        
        old_state = trade["status"]
        
        cursor.execute("""
            UPDATE trades SET status = 'FAILED', closed_at = ? WHERE id = ?
        """, (now, trade_id))
        
        cursor.execute("""
            INSERT INTO trade_ledger (
                trade_id, event_type, old_state, new_state,
                bot_type, reason, timestamp
            ) VALUES (?, 'FAILED', ?, 'FAILED', ?, ?, ?)
        """, (trade_id, old_state, trade["bot_type"], reason, now))
        
        return True


def get_trade_history_from_ledger(
    trade_id: Optional[int] = None,
    bot_type: Optional[str] = None,
    limit: int = 100
) -> List[Dict]:
    """
    Get immutable trade history from ledger.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    query = "SELECT * FROM trade_ledger WHERE 1=1"
    params = []
    
    if trade_id:
        query += " AND trade_id = ?"
        params.append(trade_id)
    
    if bot_type:
        query += " AND bot_type = ?"
        params.append(bot_type)
    
    query += " ORDER BY timestamp DESC LIMIT ?"
    params.append(limit)
    
    cursor.execute(query, params)
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]


def get_daily_pnl_by_bot(bot_type: str) -> float:
    """Get today's realized PnL for a specific bot type."""
    conn = get_connection()
    cursor = conn.cursor()
    
    from datetime import date
    today = date.today().isoformat()
    
    cursor.execute("""
        SELECT COALESCE(SUM(pnl), 0) as total_pnl
        FROM trade_ledger
        WHERE bot_type = ? 
          AND event_type = 'CLOSED'
          AND DATE(timestamp) = ?
    """, (bot_type, today))
    
    row = cursor.fetchone()
    conn.close()
    
    return float(row["total_pnl"]) if row else 0.0


# =========================
# CLI INIT
# =========================
if __name__ == "__main__":
    init_db()
