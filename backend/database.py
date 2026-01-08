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
            
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            closed_at DATETIME
        )
    ''')
    
    conn.commit()
    conn.close()
    print("Database berhasil di-reset dengan struktur baru!")

if __name__ == "__main__":
    init_db()