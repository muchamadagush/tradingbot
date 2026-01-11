# 📋 Analytics - Data Structure Reference

Panduan lengkap tentang struktur data yang digunakan oleh analytics module.

---

## 📁 Solana Data Source: `solana_trades.json`

### Lokasi File
```
backend/solana_trades.json
```

### Struktur Data (per trade)
```json
{
  "id": "SOL-1704110400",
  "timestamp": "2024-01-01T10:40:00",
  "symbol": "TOKEN/SOL",
  "side": "BUY" | "SELL",
  "price": 0,
  "amount_in": 1.0,
  "amount_out": 100.0,
  "token_address": "EPjFWaLb3odcccccc...",
  "txid": "abc123def456...",
  "status": "Success" | "Failed" | "Pending",
  "source": "Jupiter"
}
```

### Field Explanation

| Field | Type | Deskripsi | Untuk Analytics |
|-------|------|-----------|-----------------|
| `id` | string | Unique identifier | Ignored |
| `timestamp` | ISO string | Waktu transaksi | ✅ Used for filtering/grouping |
| `symbol` | string | Trading pair (TOKEN/SOL) | Ignored |
| `side` | enum | BUY atau SELL | Ignored |
| `price` | number | Price per unit | Ignored |
| `amount_in` | number | Input amount | ✅ Used for P/L calc |
| `amount_out` | number | Output amount | ✅ Used for P/L calc |
| `token_address` | string | Token mint address | Ignored |
| `txid` | string | Transaction ID | Ignored |
| `status` | enum | Success/Failed/Pending | ✅ **FILTERED: Only "Success"** |
| `source` | string | Source (Jupiter) | Ignored |

### Analytics Process
```
1. Load all trades dari JSON
2. Filter: status == "Success" ONLY
3. Parse timestamp → datetime
4. Filter by start_date (if provided)
5. Filter by end_date (if provided)
6. Calculate: profit_sol = amount_out - amount_in
7. Resample: group by timeframe (daily/weekly/monthly/yearly)
8. Calculate cumulative profit
9. Return with summary metrics
```

### Example Valid Trade
```json
{
  "id": "SOL-1704110400",
  "timestamp": "2024-01-01T10:40:00.123456",
  "symbol": "USDC/SOL",
  "side": "BUY",
  "price": 0,
  "amount_in": 1.0,
  "amount_out": 100.0,
  "token_address": "EPjFWaLb3odcccccc...",
  "txid": "5K8rZWHT9yVJ2kZxXwQaVvUvKbAo1ZxJxZp4xQ2q1R3sPvWq8q",
  "status": "Success",
  "source": "Jupiter"
}
```

### Example Invalid Trade (Ignored)
```json
{
  "id": "SOL-1704110401",
  "timestamp": "2024-01-01T10:41:00",
  "symbol": "USDC/SOL",
  "side": "SELL",
  "amount_in": 100.0,
  "amount_out": 0.9,
  "status": "Failed",  // ❌ IGNORED - not "Success"
  "source": "Jupiter"
}
```

---

## 🗄️ Tokocrypto Data Source: SQLite Database

### Lokasi Database
```
backend/crypto_bot.db
```

### Table: `trades`

#### Schema
```sql
CREATE TABLE trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,              -- 'BUY'
    buy_price REAL NOT NULL,
    amount REAL NOT NULL,
    total_usdt REAL NOT NULL,
    
    status TEXT DEFAULT 'OPEN',      -- 'OPEN' or 'CLOSED'
    sell_price REAL,
    profit_usdt REAL,                -- P/L dalam USDT
    
    fee_paid REAL DEFAULT 0,
    mode TEXT DEFAULT 'LIVE',        -- 'LIVE', 'PAPER', 'BACKTEST'
    
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    closed_at DATETIME
)
```

#### Field Explanation (untuk Analytics)

| Field | Type | Deskripsi | Untuk Analytics |
|-------|------|-----------|-----------------|
| `id` | int | Primary key | Ignored |
| `symbol` | string | Trading pair | Ignored |
| `side` | string | BUY/SELL | Ignored |
| `buy_price` | float | Entry price | Ignored (profit_usdt used) |
| `amount` | float | Amount | Ignored |
| `total_usdt` | float | Total investment | Ignored |
| `status` | enum | OPEN/CLOSED | ✅ **FILTERED: Only "CLOSED"** |
| `sell_price` | float | Exit price | Ignored (profit_usdt used) |
| `profit_usdt` | float | Realized P/L | ✅ **USED directly** |
| `fee_paid` | float | Trading fees | Ignored |
| `mode` | enum | LIVE/PAPER/BACKTEST | Ignored |
| `created_at` | datetime | Entry time | Ignored |
| `closed_at` | datetime | Exit time | ✅ **Used for filtering/grouping** |

### Analytics Process
```
1. Query database: SELECT * FROM trades WHERE status='CLOSED' AND profit_usdt IS NOT NULL
2. Filter by closed_at >= start_date (if provided)
3. Filter by closed_at <= end_date (if provided)
4. Convert to pandas DataFrame
5. Resample: group by timeframe (daily/weekly/monthly/yearly)
6. Calculate cumulative profit
7. Return with summary metrics
```

### Example Valid Trade (CLOSED)
```
id: 42
symbol: BTC/USDT
side: BUY
buy_price: 65000.0
amount: 0.01
total_usdt: 650.0
status: CLOSED           ← ✅ Required
sell_price: 67000.0
profit_usdt: 200.0      ← ✅ Used directly
fee_paid: 2.5
mode: LIVE
created_at: 2024-01-01 10:00:00
closed_at: 2024-01-01 15:30:00  ← ✅ Used for grouping
```

### Example Invalid Trade (OPEN)
```
id: 43
symbol: ETH/USDT
side: BUY
buy_price: 2500.0
amount: 1.0
total_usdt: 2500.0
status: OPEN            ← ❌ IGNORED - not "CLOSED"
sell_price: NULL
profit_usdt: NULL
mode: LIVE
created_at: 2024-01-02 10:00:00
closed_at: NULL
```

---

## 📊 Analytics Output Structure

### Response Format

#### Solana Response
```json
{
  "data": [
    {
      "date": "2024-01-01",
      "profit_sol": 0.5,                 // amount_out - amount_in
      "profit_usd": 100.0,               // profit_sol * sol_to_usd_rate
      "cumulative_profit_sol": 0.5,      // Running total
      "cumulative_profit_usd": 100.0     // Running total
    },
    {
      "date": "2024-01-02",
      "profit_sol": -0.2,                // Negative = loss
      "profit_usd": -40.0,
      "cumulative_profit_sol": 0.3,      // 0.5 + (-0.2)
      "cumulative_profit_usd": 60.0      // 100 + (-40)
    }
  ],
  "summary": {
    "total_profit_sol": 1.5,             // Sum of all positive profits
    "total_profit_usd": 300.0,
    "total_loss_sol": -0.8,              // Sum of all negative profits
    "total_loss_usd": -160.0,
    "net_profit_sol": 0.7,               // total_profit + total_loss
    "net_profit_usd": 140.0,
    "total_trades": 10,                  // Count
    "winning_trades": 7,                 // Count where profit > 0
    "losing_trades": 3,                  // Count where profit < 0
    "win_rate": 70.0                     // (winning_trades / total_trades) * 100
  }
}
```

#### Tokocrypto Response
```json
{
  "data": [
    {
      "date": "2024-01-01",
      "profit_usdt": 250.5,              // From database
      "cumulative_profit": 250.5         // Running total
    },
    {
      "date": "2024-01-08",
      "profit_usdt": -100.2,             // Negative = loss
      "cumulative_profit": 150.3         // 250.5 + (-100.2)
    }
  ],
  "summary": {
    "total_profit_usdt": 1500.75,        // Sum of positive
    "total_loss_usdt": -300.25,          // Sum of negative
    "net_profit_usdt": 1200.5,           // total_profit + total_loss
    "total_trades": 25,
    "winning_trades": 18,
    "losing_trades": 7,
    "win_rate": 72.0
  }
}
```

---

## 🔄 Timeframe Grouping

Analytics menggunakan pandas resample untuk grouping data.

### Mapping

| Timeframe | Pandas Freq | Grouping | Example Date Format |
|-----------|-------------|----------|---------------------|
| `daily` | `D` | Hari | 2024-01-01 |
| `weekly` | `W` | Minggu | 2024-W01 |
| `monthly` | `M` | Bulan | 2024-01 (per bulan) |
| `yearly` | `Y` | Tahun | 2024-01 (per tahun) |

### Contoh Grouping

**Daily:**
```
2024-01-01: [semua trades dengan timestamp 2024-01-01]
2024-01-02: [semua trades dengan timestamp 2024-01-02]
2024-01-03: [semua trades dengan timestamp 2024-01-03]
```

**Weekly:**
```
2024-W01: [semua trades minggu 1 tahun 2024]
2024-W02: [semua trades minggu 2 tahun 2024]
```

**Monthly:**
```
2024-01: [semua trades di bulan Januari 2024]
2024-02: [semua trades di bulan Februari 2024]
```

---

## 🧮 Profit Calculation Details

### Solana Profit Calculation

**Formula:**
```
profit_sol = amount_out - amount_in
profit_usd = profit_sol * sol_to_usd_rate (default: 200.0)
```

**Contoh BUY Trade:**
```
amount_in: 1.0 SOL (input)
amount_out: 100.0 USDC (output)
profit_sol = 100.0 - 1.0 = 99.0
profit_usd = 99.0 * 200 = 19,800.0

Interpretasi: 
- Membeli 100 USDC dengan 1 SOL
- Profit dihitung dalam satuan SOL equivalent
```

**Catatan:** Konsep profit di sini lebih merupakan "value change" dalam trade, bukan realized gain/loss terhadap basis awal.

### Tokocrypto Profit Calculation

**Formula:**
```
profit_usdt = database field 'profit_usdt'
            = (sell_price - buy_price) * amount
```

**Contoh:**
```
buy_price: 50000
sell_price: 52000
amount: 0.01 BTC
profit_usdt = (52000 - 50000) * 0.01 = 200 USDT
```

---

## ⚠️ Important Notes

### Data Integrity

1. **Solana Trades:**
   - Status harus case-sensitive: `"Success"` (tidak `"success"`)
   - Timestamp harus ISO format
   - amount_in dan amount_out harus numeric

2. **Tokocrypto Trades:**
   - Status harus: `'CLOSED'` (UPPERCASE)
   - profit_usdt harus NOT NULL untuk diperhitungkan
   - closed_at harus valid datetime

### Edge Cases

1. **Empty Data:**
   - Jika tidak ada trades yang match filter
   - Returns: `"data": []` dan summary dengan semua zeros

2. **Date Range Ordering:**
   - start_date > end_date tidak ada validasi
   - Hasil akan empty

3. **Invalid Timeframe:**
   - Default ke `'D'` (daily) jika nilai tidak dikenal

---

## 🔍 Debugging Tips

### Check Solana Data
```bash
# Print first trade
cat backend/solana_trades.json | head -20

# Count total trades
cat backend/solana_trades.json | grep -c '"status": "Success"'
```

### Check Tokocrypto Data
```bash
# Query closed trades
sqlite3 backend/crypto_bot.db "SELECT COUNT(*) FROM trades WHERE status='CLOSED' AND profit_usdt IS NOT NULL;"

# View sample trade
sqlite3 backend/crypto_bot.db "SELECT * FROM trades WHERE status='CLOSED' LIMIT 1;"
```

### Test Analytics Directly
```python
# In Python REPL
import analytics
import json

# Test Solana
result = analytics.calculate_solana_analytics()
print(json.dumps(result, indent=2))

# Test Tokocrypto
result = analytics.calculate_tokocrypto_analytics()
print(json.dumps(result, indent=2))
```

---

## 📚 Related Files

- [Analytics API Docs](./ANALYTICS_API_DOCS.md)
- [Implementation Summary](./ANALYTICS_IMPLEMENTATION_SUMMARY.md)
- [Quick Start Guide](./ANALYTICS_QUICK_START.md)
- [Source Code](./backend/analytics.py)

