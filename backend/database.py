import sqlite3

def get_connection():
    conn = sqlite3.connect('crypto_bot.db')
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Tabel History Transaksi (Lebih Lengkap)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            side TEXT NOT NULL,      -- 'BUY'
            buy_price REAL NOT NULL,
            amount REAL NOT NULL,
            total_usdt REAL NOT NULL,
            
            status TEXT DEFAULT 'OPEN', -- 'OPEN' (Sedang dihold) atau 'CLOSED' (Sudah dijual)
            sell_price REAL,            -- Diisi saat jual
            profit_usdt REAL,           -- Diisi saat jual
            
            fee_paid REAL DEFAULT 0,    -- Trading fee yang dibayar
            mode TEXT DEFAULT 'LIVE',   -- 'LIVE', 'PAPER', 'BACKTEST'
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME
        )
    ''')
    
    # Tabel untuk Backtest Results
    cursor.execute('''
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
            result_json TEXT,  -- Full JSON result
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabel untuk Paper Trading State (backup)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS paper_trading_snapshots (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            balance REAL NOT NULL,
            total_equity REAL NOT NULL,
            total_pnl REAL NOT NULL,
            open_positions INTEGER NOT NULL,
            snapshot_json TEXT,  -- Full state JSON
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized with extended schema!")

def save_backtest_result(result):
    """Save backtest result to database"""
    conn = get_connection()
    cursor = conn.cursor()
    
    import json
    cursor.execute('''
        INSERT INTO backtest_results 
        (symbol, timeframe, period_days, initial_capital, final_capital, roi_pct, 
         total_trades, win_rate_pct, max_drawdown_pct, profit_factor, total_fees_paid, result_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        result['symbol'],
        result['timeframe'],
        result['period_days'],
        result['initial_capital'],
        result['final_capital'],
        result['roi_pct'],
        result['total_trades'],
        result['win_rate_pct'],
        result['max_drawdown_pct'],
        result['profit_factor'],
        result['total_fees_paid'],
        json.dumps(result, default=str)
    ))
    
    conn.commit()
    backtest_id = cursor.lastrowid
    conn.close()
    return backtest_id

def get_backtest_history(limit=10):
    """Get backtest history"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT * FROM backtest_results 
        ORDER BY created_at DESC 
        LIMIT ?
    ''', (limit,))
    results = cursor.fetchall()
    conn.close()
    return results

if __name__ == "__main__":
    init_db()