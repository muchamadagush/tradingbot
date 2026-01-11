# 🚀 Analytics Feature - Quick Start Guide

## Apa yang Ditambahkan?

Fitur analytics untuk melacak profit/loss dari trading activities di Solana dan Tokocrypto.

---

## 📍 File Lokasi

### File Baru
```
backend/analytics.py              ← Module logic utama (355 lines)
backend/test_analytics.py         ← Unit tests
ANALYTICS_API_DOCS.md             ← Dokumentasi lengkap
ANALYTICS_IMPLEMENTATION_SUMMARY.md ← Summary implementasi
```

### File Termodifikasi
```
backend/main.py                   ← +import analytics, +2 endpoints
```

---

## ⚡ Quick Start

### 1. Jalankan Backend Seperti Biasa
```bash
cd backend
pip install -r requirements.txt  # pandas sudah included
uvicorn main:app --reload
```

### 2. Test Endpoints

**Solana Analytics:**
```bash
curl "http://127.0.0.1:8000/api/analytics/solana"
```

**Tokocrypto Analytics:**
```bash
curl "http://127.0.0.1:8000/api/analytics/tokocrypto"
```

**Dengan Filter:**
```bash
curl "http://127.0.0.1:8000/api/analytics/solana?start_date=2024-01-01&timeframe=weekly"
```

---

## 📊 API Response Format

### Solana Response
```json
{
  "data": [
    {
      "date": "2024-01-01",
      "profit_sol": 0.5,
      "profit_usd": 100.0,
      "cumulative_profit_sol": 0.5,
      "cumulative_profit_usd": 100.0
    }
  ],
  "summary": {
    "total_profit_sol": 5.0,
    "total_profit_usd": 1000.0,
    "total_loss_sol": -2.0,
    "total_loss_usd": -400.0,
    "net_profit_sol": 3.0,
    "net_profit_usd": 600.0,
    "total_trades": 20,
    "winning_trades": 15,
    "losing_trades": 5,
    "win_rate": 75.0
  }
}
```

### Tokocrypto Response
```json
{
  "data": [
    {
      "date": "2024-01-01",
      "profit_usdt": 100,
      "cumulative_profit": 100
    }
  ],
  "summary": {
    "total_profit_usdt": 500,
    "total_loss_usdt": -200,
    "net_profit_usdt": 300,
    "total_trades": 20,
    "winning_trades": 15,
    "losing_trades": 5,
    "win_rate": 75.0
  }
}
```

---

## 🔍 Query Parameters

| Parameter | Type | Default | Example |
|-----------|------|---------|---------|
| `start_date` | string | none | `2024-01-01` |
| `end_date` | string | none | `2024-01-31` |
| `timeframe` | string | `daily` | `weekly`, `monthly`, `yearly` |

---

## 🧪 Jalankan Tests

```bash
cd backend
python test_analytics.py
```

Expected output:
```
============================================================
TEST 1: Solana Analytics - Empty Data
============================================================
✅ Empty data test passed

============================================================
TEST 2: Solana Analytics - Mock Data
...
✅ Mock data test passed

...

======================================================================
✅ ALL TESTS PASSED!
======================================================================
```

---

## 🔒 Jaminan Keamanan

✅ **Core trading logic TIDAK berubah:**
- Auto trading loop tetap berjalan
- Strategy manager tetap aktif
- Risk management tetap enforced
- Database struktur tetap sama

✅ **Analytics adalah READ-ONLY:**
- Tidak mengubah data apapun
- Tidak mengirim order
- Tidak mempengaruhi trading

---

## 📈 Cara Integrasi ke Frontend

### Option 1: Display dalam Tab Baru
```jsx
// frontend/src/components/AnalyticsTab.jsx
function AnalyticsTab() {
  const [solanaData, setSolanaData] = useState(null);
  
  useEffect(() => {
    axios.get('/api/analytics/solana?timeframe=daily')
      .then(res => setSolanaData(res.data))
      .catch(err => console.error(err));
  }, []);
  
  return (
    <div>
      {/* Render chart dengan solanaData */}
    </div>
  );
}
```

### Option 2: Add ke Existing Dashboard
```jsx
// Tambahkan ke DashboardTab.jsx
const analyticsResponse = await axios.get('/api/analytics/tokocrypto?timeframe=daily');
```

---

## 🎯 Features

### Solana Analytics
- ✅ Read dari `solana_trades.json`
- ✅ Filter by date range
- ✅ Resample by timeframe (daily/weekly/monthly/yearly)
- ✅ Calculate profit (Output - Input dalam SOL)
- ✅ Convert ke USD (default 1 SOL = $200)
- ✅ Summary metrics (win rate, total trades, etc)

### Tokocrypto Analytics  
- ✅ Query dari SQLite database
- ✅ Filter by date range
- ✅ Resample by timeframe
- ✅ Calculate realized P/L (dari database)
- ✅ Summary metrics

---

## 🚨 Troubleshooting

### "ModuleNotFoundError: No module named 'pandas'"
```bash
pip install pandas==2.1.3
```

### "ModuleNotFoundError: No module named 'analytics'"
- Pastikan `backend/analytics.py` ada di folder `backend/`
- Pastikan import di `main.py`: `import analytics`

### Response kosong (empty data)
- **Solana:** Pastikan ada data di `backend/solana_trades.json` dengan `status: "Success"`
- **Tokocrypto:** Pastikan ada closed trades di database dengan `status = 'CLOSED'`

### Wrong profit calculation
- **Solana:** Profit = `amount_out - amount_in`
- **Tokocrypto:** Profit = dari field `profit_usdt` di database

---

## 📚 Documentation Files

1. **ANALYTICS_API_DOCS.md** - Dokumentasi lengkap API
2. **ANALYTICS_IMPLEMENTATION_SUMMARY.md** - Summary implementasi
3. **backend/test_analytics.py** - Unit tests
4. **backend/analytics.py** - Source code dengan docstrings

---

## 💡 Tips

1. **Cache Results:** Untuk query yang sama, cache hasilnya di frontend untuk performa lebih baik
2. **Real SOL Price:** Update `sol_to_usd` parameter dengan price dari Jupiter API
3. **Large Datasets:** Gunakan `start_date` dan `end_date` untuk membatasi hasil
4. **Timeframe Selection:** Default `daily` bagus untuk trend, `weekly` bagus untuk overview

---

## ❓ FAQ

**Q: Apakah ini mempengaruhi trading bot?**
A: Tidak sama sekali. Analytics hanya membaca data, tidak mengubah apapun.

**Q: Bisa untuk real-time data?**
A: Endpoint ini mengembalikan historical data. Untuk real-time, tambahkan WebSocket.

**Q: Bisa custom timeframe?**
A: Saat ini support: daily, weekly, monthly, yearly. Bisa ditambahkan hourly jika perlu.

**Q: Berapa lama query berjalan?**
A: Tergantung jumlah trades. Untuk dataset kecil (<1000), instant. Untuk besar, bisa 1-2 detik.

---

## 🎓 Learn More

- [Pandas Resampling Docs](https://pandas.pydata.org/docs/reference/api/pandas.DataFrame.resample.html)
- [FastAPI Query Parameters](https://fastapi.tiangolo.com/tutorial/query-parameters/)
- [Our Full Analytics Documentation](./ANALYTICS_API_DOCS.md)

---

**Happy analyzing! 📊**

