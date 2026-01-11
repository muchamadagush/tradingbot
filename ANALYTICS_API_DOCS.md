# Analytics API Documentation

## 📊 Fitur Baru: Analytics untuk Profit/Loss Tracking

Fitur analytics telah ditambahkan ke backend untuk menghitung profit/loss dari trading activities di Solana dan Tokocrypto.

### Implementasi

#### File Baru
- **`backend/analytics.py`** - Module logic untuk menghitung analytics
  - `calculate_solana_analytics()` - Hitung P/L untuk Solana trades dari JSON
  - `calculate_tokocrypto_analytics()` - Hitung P/L untuk Tokocrypto trades dari SQLite

#### File Termodifikasi
- **`backend/main.py`** - Tambahan 2 endpoint baru
  - Added: `import analytics` (line 19)
  - Added: `GET /api/analytics/solana` (line 803-852)
  - Added: `GET /api/analytics/tokocrypto` (line 855-898)

---

## 📡 API Endpoints

### 1. GET /api/analytics/solana

**Deskripsi:** Mendapatkan analisis profit/loss untuk trading Solana berdasarkan data dari `solana_trades.json`

**Query Parameters:**
| Parameter | Type | Required | Format | Deskripsi |
|-----------|------|----------|--------|-----------|
| `start_date` | string | No | YYYY-MM-DD | Tanggal awal filter |
| `end_date` | string | No | YYYY-MM-DD | Tanggal akhir filter |
| `timeframe` | string | No | daily\|weekly\|monthly\|yearly | Default: `daily` |

**Example Request:**
```
GET /api/analytics/solana?start_date=2024-01-01&end_date=2024-01-31&timeframe=daily
```

**Response Success (200):**
```json
{
  "data": [
    {
      "date": "2024-01-01",
      "profit_sol": 0.5,
      "profit_usd": 100.0,
      "cumulative_profit_sol": 0.5,
      "cumulative_profit_usd": 100.0
    },
    {
      "date": "2024-01-02",
      "profit_sol": -0.2,
      "profit_usd": -40.0,
      "cumulative_profit_sol": 0.3,
      "cumulative_profit_usd": 60.0
    }
  ],
  "summary": {
    "total_profit_sol": 1.5,
    "total_profit_usd": 300.0,
    "total_loss_sol": -0.8,
    "total_loss_usd": -160.0,
    "net_profit_sol": 0.7,
    "net_profit_usd": 140.0,
    "total_trades": 10,
    "winning_trades": 7,
    "losing_trades": 3,
    "win_rate": 70.0
  }
}
```

**Catatan:**
- Hanya memproses transaksi dengan status `"Success"`
- Profit dihitung sebagai: `amount_out - amount_in` (dalam SOL)
- Konversi USD menggunakan rate default 1 SOL = $200 (bisa dikonfigurasi)

---

### 2. GET /api/analytics/tokocrypto

**Deskripsi:** Mendapatkan analisis profit/loss untuk trading Tokocrypto berdasarkan data dari SQLite database

**Query Parameters:**
| Parameter | Type | Required | Format | Deskripsi |
|-----------|------|----------|--------|-----------|
| `start_date` | string | No | YYYY-MM-DD | Tanggal awal filter |
| `end_date` | string | No | YYYY-MM-DD | Tanggal akhir filter |
| `timeframe` | string | No | daily\|weekly\|monthly\|yearly | Default: `daily` |

**Example Request:**
```
GET /api/analytics/tokocrypto?start_date=2024-01-01&end_date=2024-01-31&timeframe=weekly
```

**Response Success (200):**
```json
{
  "data": [
    {
      "date": "2024-01-01",
      "profit_usdt": 250.5,
      "cumulative_profit": 250.5
    },
    {
      "date": "2024-01-08",
      "profit_usdt": -100.2,
      "cumulative_profit": 150.3
    }
  ],
  "summary": {
    "total_profit_usdt": 1500.75,
    "total_loss_usdt": -300.25,
    "net_profit_usdt": 1200.5,
    "total_trades": 25,
    "winning_trades": 18,
    "losing_trades": 7,
    "win_rate": 72.0
  }
}
```

**Catatan:**
- Hanya memproses transaksi dengan status `'CLOSED'` (sudah ditutup)
- Profit dihitung dari field `profit_usdt` di database (selisih sell_price - buy_price)
- Grouping dilakukan berdasarkan `closed_at` timestamp

---

## 📐 Technical Details

### Data Sources

#### Solana Analytics
- **Source:** `backend/solana_trades.json`
- **Status Filter:** Hanya transaksi dengan `status == "Success"`
- **Struktur data:**
  ```json
  {
    "timestamp": "2024-01-01T10:30:00",
    "symbol": "TOKEN/SOL",
    "side": "BUY" | "SELL",
    "amount_in": 1.0,
    "amount_out": 0.5,
    "status": "Success"
  }
  ```

#### Tokocrypto Analytics
- **Source:** SQLite database (`crypto_bot.db`) - table `trades`
- **Status Filter:** Hanya transaksi dengan `status == 'CLOSED'`
- **Field yang digunakan:**
  - `buy_price` - Harga beli
  - `sell_price` - Harga jual
  - `profit_usdt` - P/L yang sudah dihitung
  - `closed_at` - Timestamp penutupan

### Logika Kalkulasi

#### Solana (dalam SOL)
```
profit_per_trade = amount_out - amount_in
profit_usd = profit_per_trade * sol_to_usd_rate
```

#### Tokocrypto (dalam USDT)
```
profit_usdt = sell_price - buy_price (dari database)
```

### Timeframe Grouping (Pandas Resampling)
- `daily` → Resample by Day (D)
- `weekly` → Resample by Week (W)
- `monthly` → Resample by Month (M)
- `yearly` → Resample by Year (Y)

### Summary Metrics

Kedua endpoint menghitung metrics yang sama:
- **Total Profit:** Sum dari semua profitable trades
- **Total Loss:** Sum dari semua losing trades (negatif)
- **Net Profit:** Total Profit + Total Loss
- **Total Trades:** Count seluruh transaksi
- **Winning Trades:** Count transaksi dengan profit > 0
- **Losing Trades:** Count transaksi dengan profit < 0
- **Win Rate:** (Winning Trades / Total Trades) × 100%

---

## 🔧 Integration Notes

### Tidak Mengubah Core Logic
✅ Semua fitur analytics **HANYA MEMBACA DATA** - tidak mengubah:
- Logic trading bot
- Strategy manager
- Risk management
- Paper trading state
- Database struktur

### Dependency Requirements
```
pandas==2.1.3  # Untuk resampling dan grouping data
```

### Usage dalam Frontend

Endpoints ini siap diintegrasikan ke frontend untuk menampilkan:
- **Chart:** Profit/Loss per timeframe
- **Summary:** Total trades, win rate, profitability
- **Cumulative Profit:** Trend keuntungan dari waktu ke waktu

### Testing Endpoints

```bash
# Test Solana Analytics
curl "http://127.0.0.1:8000/api/analytics/solana?timeframe=daily"

# Test Tokocrypto Analytics  
curl "http://127.0.0.1:8000/api/analytics/tokocrypto?start_date=2024-01-01&timeframe=weekly"
```

---

## 📝 Error Handling

Kedua endpoint mengembalikan struktur yang sama meski tidak ada data:
```json
{
  "data": [],
  "summary": {
    "total_profit_sol": 0.0,
    "total_profit_usd": 0.0,
    "total_loss_sol": 0.0,
    "total_loss_usd": 0.0,
    "net_profit_sol": 0.0,
    "net_profit_usd": 0.0,
    "total_trades": 0,
    "winning_trades": 0,
    "losing_trades": 0,
    "win_rate": 0.0
  }
}
```

---

## 🎯 Future Enhancements

1. **Fetch Real SOL Price:** Integrate Jupiter API untuk mendapatkan real-time SOL price
2. **Database Optimization:** Add indexes ke `closed_at` di table trades untuk query lebih cepat
3. **Advanced Metrics:** Tambahkan Sharpe Ratio, Sortino Ratio, Maximum Drawdown
4. **Caching:** Implement result caching untuk date ranges yang tidak berubah
5. **Export:** Tambahkan endpoint untuk export data ke CSV/Excel

