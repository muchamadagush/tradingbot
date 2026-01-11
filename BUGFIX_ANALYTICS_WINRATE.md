# 📊 Analytics Win Rate Fix - SELL-Side Only Metrics

**Status:** ✅ FIXED  
**File:** `backend/analytics.py` - Fungsi `calculate_solana_analytics()`  
**Date:** 2026-01-11  
**Issue:** Win Rate dan Total Trades dihitung salah karena BUY trades ikut dihitung sebagai Winning/Losing

---

## Problem

Sebelumnya, `winning_trades` dan `losing_trades` dihitung dari **semua transaksi (BUY + SELL)**. Ini salah karena:

```python
# OLD BUGGY LOGIC
winning_trades = len(df[df['profit_sol'] > 0])  # Hitung semua profit > 0
losing_trades = len(df[df['profit_sol'] < 0])   # Hitung semua profit < 0
total_trades = len(df)                           # Semua transaksi (BUY + SELL)
```

### Contoh Masalah:
```
BUY 1000 COPE dengan -0.5 SOL (keluar uang)
  profit_sol = -0.5 → DIHITUNG SEBAGAI "losing_trades" ❌ SALAH!
  (BUY adalah entry, bukan trade completion)

SELL 1000 COPE dengan +0.48 SOL (masuk uang)
  profit_sol = +0.48 → DIHITUNG SEBAGAI "winning_trades" ✅ BENAR

Hasil Perhitungan Lama:
  total_trades = 2 (BUY + SELL)
  winning_trades = 1 (SELL)
  losing_trades = 1 (BUY) ❌ SEHARUSNYA TIDAK DIHITUNG
  win_rate = 50% ❌ SEHARUSNYA 100% (1 dari 1 SELL berhasil)
```

---

## Solution: SELL-Side Only Metrics

Logika baru: **Hitung metrics hanya dari transaksi SELL (exit trades)**, bukan BUY (entry).

**Alasan:**
- **BUY adalah entry** → tidak ada win/loss di sini, hanya modal keluar
- **SELL adalah exit** → di sini baru ada hasil (win/loss)
- **Win/loss ratio** harus diukur dari exit, bukan entry

### Implementasi:

```python
# STEP 1: Filter hanya SELL transaksi
df_sell = df[df['side'].str.upper() == 'SELL']

# STEP 2: Total Trades = jumlah SELL transaksi saja
total_trades = len(df_sell)

# STEP 3: Winning Trades = SELL dengan status TP/Profit/Win/Success (tanpa SL)
if total_trades > 0:
    winning_trades = 0
    for idx, row in df_sell.iterrows():
        status = str(row.get('status', '')).upper()
        has_winning_indicator = ('TP' in status or 'PROFIT' in status or 
                                 'WIN' in status or 'SUCCESS' in status)
        has_losing_indicator = ('SL' in status or 'LOSS' in status or 'CUT' in status)
        
        if has_winning_indicator and not has_losing_indicator:
            winning_trades += 1

# STEP 4: Losing Trades = SELL dengan status SL/Loss/Cut
    losing_trades = 0
    for idx, row in df_sell.iterrows():
        status = str(row.get('status', '')).upper()
        has_losing_indicator = ('SL' in status or 'LOSS' in status or 'CUT' in status)
        
        if has_losing_indicator:
            losing_trades += 1

# STEP 5: Win Rate = winning_trades / total_trades
win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
```

---

## Key Rules

| Metrik | Logika | Contoh |
|--------|--------|--------|
| **Total Trades** | Jumlah SELL transaksi | 10 SELL (ignore 10 BUY) |
| **Winning Trades** | SELL dengan status: TP, Profit, Win, Success (NO SL) | "✅ TP Hit Success" → WIN |
| **Losing Trades** | SELL dengan status: SL, Loss, Cut | "❌ SL Hit @ $5" → LOSS |
| **Win Rate** | winning_trades / total_trades × 100% | 8 win / 10 exit = 80% |
| **Net Profit** | Sum semua cashflow (BUY + SELL) | -0.5 (BUY) + 0.48 (SELL) = -0.02 |

### Status Examples:
```
✅ WINNING SELL:
  - "✅ TP Hit Success"
  - "Take Profit"
  - "Win: +0.5 SOL"
  - "Closed with Profit"

❌ LOSING SELL:
  - "❌ SL Hit @ $5"
  - "Stop Loss"
  - "Cut Loss @ 0.45"
  - "Closed at Loss"

⚠️ NEUTRAL (tidak masuk kategori):
  - "Closed" (tanpa indicator)
  - "Cancelled" (tidak ada exit)
```

---

## Before & After Example

### Scenario: 2 COPE Trades
```
Trade A: BUY 1000 COPE
  side: BUY
  amount_in: 0.5 SOL
  status: "Success"
  profit_sol: -0.5

Trade B: SELL 1000 COPE
  side: SELL
  amount_out: 0.48 SOL
  status: "✅ SL Hit @ 0.48"
  profit_sol: +0.48
```

### OLD BUGGY CALCULATION ❌
```
winning_trades = 1 (SELL with +0.48)
losing_trades = 1 (BUY with -0.5) ❌ SALAH! BUY tidak boleh counted
total_trades = 2 (BUY + SELL)
win_rate = 1/2 = 50% ❌ SALAH!
```

### NEW FIXED CALCULATION ✅
```
df_sell = [Trade B only] (filter SELL only)
total_trades = 1 (hanya SELL)

Trade B status = "✅ SL Hit @ 0.48"
  has_losing_indicator = 'SL' in status → TRUE
  losing_trades = 1

winning_trades = 0 (status punya SL, tidak TP/Win)
win_rate = 0/1 = 0% ✅ BENAR! (1 exit loss, no win)
```

---

## Chart vs Summary Behavior

### Data (Chart) - TETAP PAKAI SEMUA TRANSAKSI
```python
# Cumulative profit graph masih menampilkan arus kas real
# BUY (-0.5) → SELL (+0.48) → Net: -0.02

data: [
  {
    "date": "2024-01-15",
    "profit_sol": -0.5,      # BUY
    "cumulative_profit_sol": -0.5
  },
  {
    "date": "2024-01-15",
    "profit_sol": +0.48,     # SELL
    "cumulative_profit_sol": -0.02
  }
]
```
✅ Chart tetap akurat menampilkan arus kas harian (semua transaksi)

### Summary (Metrics) - HANYA DARI SELL
```python
summary: {
  "total_profit_sol": 0.48,          # Sum profit > 0 (all trades)
  "total_loss_sol": -0.5,            # Sum profit < 0 (all trades)
  "net_profit_sol": -0.02,           # Total (all trades)
  
  "total_trades": 1,                 # Only SELL trades
  "winning_trades": 0,               # SELL with TP/Win indicators
  "losing_trades": 1,                # SELL with SL/Loss indicators
  "win_rate": 0.0                    # 0 win / 1 exit = 0%
}
```
✅ Metrics hanya fokus pada exit performance (SELL saja)

---

## Testing

### Test Case 1: Pure Winner
```
BUY + SELL with TP Hit
Expected:
  total_trades: 1
  winning_trades: 1
  losing_trades: 0
  win_rate: 100%
```

### Test Case 2: Pure Loser
```
BUY + SELL with SL Hit
Expected:
  total_trades: 1
  winning_trades: 0
  losing_trades: 1
  win_rate: 0%
```

### Test Case 3: Mixed
```
Trade 1: BUY + SELL (TP) → WIN
Trade 2: BUY + SELL (SL) → LOSS
Trade 3: BUY + SELL (Cut) → LOSS
Expected:
  total_trades: 3
  winning_trades: 1
  losing_trades: 2
  win_rate: 33.33%
```

---

## API Response Format

```json
{
  "data": [
    {
      "date": "2024-01-15",
      "profit_sol": -0.5,
      "profit_usd": -100.0,
      "cumulative_profit_sol": -0.5,
      "cumulative_profit_usd": -100.0
    },
    {
      "date": "2024-01-15",
      "profit_sol": 0.48,
      "profit_usd": 96.0,
      "cumulative_profit_sol": -0.02,
      "cumulative_profit_usd": -4.0
    }
  ],
  "summary": {
    "total_profit_sol": 0.48,
    "total_profit_usd": 96.0,
    "total_loss_sol": -0.5,
    "total_loss_usd": -100.0,
    "net_profit_sol": -0.02,
    "net_profit_usd": -4.0,
    "total_trades": 1,           ← SELL count only
    "winning_trades": 0,         ← SELL with TP/Win only
    "losing_trades": 1,          ← SELL with SL/Loss only
    "win_rate": 0.0              ← 0/1 = 0%
  }
}
```

---

## Code Changes Summary

**File:** `backend/analytics.py` - Lines 207-251

**Changes:**
1. ✅ Filter SELL transaksi saja: `df_sell = df[df['side'].str.upper() == 'SELL']`
2. ✅ Total trades hanya SELL: `total_trades = len(df_sell)`
3. ✅ Winning trades dengan status check: TP/Profit/Win/Success (tanpa SL)
4. ✅ Losing trades dengan status check: SL/Loss/Cut
5. ✅ Net profit tetap dari semua transaksi untuk akurasi arus kas

**Backward Compatible:** ✅ API response structure tetap sama, hanya value yang berubah (lebih akurat)

---

## Why This Matters

### Old Behavior (Misleading)
- Show 50% win rate (termasuk BUY yang bukan trade completion)
- Total trades mencakup entry (BUY) dan exit (SELL)
- Tidak bisa mengukur exit performance yang sebenarnya

### New Behavior (Accurate)
- Show 0% win rate (dari 1 exit yang loss)
- Total trades hanya exit (SELL)
- Bisa measure success rate dari exit strategy
- Fokus pada apa yang important: berapa % exit kami profitable

---

## Deployment

```bash
# No migration needed - pure calculation logic fix
# Frontend tidak perlu diubah - API structure sama

# Test di Analytics tab:
# 1. Check Win Rate (harus realistis, <= 100%)
# 2. Check Total Trades (harus lebih sedikit dari sebelumnya, hanya SELL)
# 3. Check summary metrics sesuai ekspektasi
```

---

## Sign-Off

✅ **Fixed By:** Analytics Win Rate Correction  
✅ **Impact:** Accurate exit performance metrics  
✅ **Status:** DEPLOYED & READY

Win rate sekarang menunjukkan **performa exit yang sebenarnya**, bukan campuran entry+exit! 🎯📈
