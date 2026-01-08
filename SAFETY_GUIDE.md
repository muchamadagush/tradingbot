# 🤖 Trading Bot - SAFE VERSION

Bot trading crypto yang AMAN dengan fitur Backtesting, Paper Trading, Fee Calculator, dan Risk Management.

## ⚠️ PERINGATAN PENTING

**JANGAN PERNAH** langsung trading dengan uang asli tanpa testing! Bot ini sekarang memiliki 3 mode:

1. **BACKTEST** - Testing strategi dengan data historis ✅ AMAN
2. **PAPER** - Trading dengan uang virtual ✅ AMAN (Default)
3. **LIVE** - Trading dengan uang asli ⚠️ BERBAHAYA!

## 🆕 Fitur Baru (Safety Features)

### ✅ Sudah Diimplementasikan:

1. **Backtesting Engine** (`backtesting.py`)
   - Test strategi dengan data historis
   - Hitung profit/loss tanpa risiko
   - ROI, win rate, max drawdown analysis
   - Support multiple timeframes (1m, 5m, 1h, 4h, 1d)

2. **Paper Trading** (`paper_trading.py`)
   - Trading dengan uang monopoli
   - Real-time market data
   - Full order & trade tracking
   - Profit/Loss calculation

3. **Fee Calculator** (`fee_calculator.py`)
   - Hitung biaya exchange (0.1-0.2%)
   - Slippage estimation
   - Break-even price calculation
   - Profit target & stop-loss calculator

4. **Risk Management** (`risk_manager.py`)
   - Position sizing otomatis
   - Max drawdown protection
   - Daily loss limit
   - Kelly Criterion
   - Volatility adjustment

5. **Extended Database**
   - Backtest results storage
   - Paper trading history
   - Fee tracking per trade

## 📦 Setup & Installation

### 1. Install Dependencies
```bash
cd backend
pip install -r requirements.txt
```

### 2. Configuration

Copy `.env.example` ke `.env` dan edit:

```bash
cp .env.example .env
```

**PENTING:** Set mode ke `PAPER` untuk testing aman:

```env
# PILIH MODE (WAJIB SET KE PAPER DULU!)
BOT_MODE=PAPER

# Paper Trading Balance
PAPER_INITIAL_BALANCE=1000.0

# Risk Management
MAX_POSITION_SIZE_PCT=20.0
MAX_PORTFOLIO_DRAWDOWN_PCT=15.0
MAX_DAILY_LOSS_PCT=5.0
RISK_PER_TRADE_PCT=2.0
```

### 3. Initialize Database

```bash
python database.py
```

### 4. Run Bot

```bash
uvicorn main:app --reload --port 8000
```

## 🧪 Testing Workflow (WAJIB!)

### Phase 1: Backtesting (Data Historis)

Test strategi dengan data masa lalu:

```bash
# Via API
curl -X POST http://localhost:8000/api/backtest/run \
  -H "Content-Type: application/json" \
  -d '{
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days_back": 30,
    "initial_capital": 1000,
    "take_profit_pct": 1.5,
    "stop_loss_pct": 3.0
  }'
```

Atau langsung via Python:

```python
import asyncio
from backtesting import BacktestEngine

async def test():
    engine = BacktestEngine(initial_capital=1000)
    result = await engine.run_backtest('BTC/USDT', timeframe='1h', days_back=30)
    print(f"ROI: {result['roi_pct']}%")
    print(f"Win Rate: {result['win_rate_pct']}%")

asyncio.run(test())
```

### Phase 2: Paper Trading (Market Real-time)

Setelah backtest sukses, test di pasar real-time dengan uang virtual:

```bash
# 1. Set BOT_MODE=PAPER di .env (sudah default)

# 2. Check paper account
curl http://localhost:8000/api/paper/account

# 3. Buy (virtual)
curl -X POST http://localhost:8000/api/paper/buy \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC/USDT", "amount_usdt": 100}'

# 4. Check position
curl http://localhost:8000/api/paper/account

# 5. Sell (virtual)
curl -X POST http://localhost:8000/api/paper/sell \
  -H "Content-Type: application/json" \
  -d '{"symbol": "BTC/USDT", "percentage": 100}'
```

### Phase 3: Live Trading (HANYA Setelah Proven Profitable)

**HANYA** jika backtest & paper trading konsisten profit selama 1-2 minggu:

```env
# .env
BOT_MODE=LIVE  # ⚠️ BAHAYA! Uang asli
```

## 📊 API Endpoints Baru

### Backtesting

```
POST /api/backtest/run          - Run single backtest
POST /api/backtest/batch        - Run multiple symbols
GET  /api/backtest/history      - Get backtest history
```

### Paper Trading

```
GET  /api/paper/account         - Account summary
POST /api/paper/buy             - Virtual buy
POST /api/paper/sell            - Virtual sell
POST /api/paper/reset           - Reset account
GET  /api/paper/orders          - Order history
GET  /api/paper/trades          - Trade history
```

### Fee Calculator

```
POST /api/fee/calculate-buy     - Calculate buy cost
POST /api/fee/calculate-sell    - Calculate sell proceeds
POST /api/fee/round-trip        - Buy + sell cost
POST /api/fee/profit-target     - Target sell price
```

### Risk Management

```
POST /api/risk/position-size    - Optimal position size
GET  /api/risk/summary          - Risk summary
POST /api/risk/kelly            - Kelly Criterion
```

## 🔍 Example: Complete Testing Flow

```python
import requests
import time

BASE_URL = "http://localhost:8000"

# 1. BACKTEST PHASE
print("Phase 1: Backtesting...")
backtest = requests.post(f"{BASE_URL}/api/backtest/run", json={
    "symbol": "BTC/USDT",
    "timeframe": "1h",
    "days_back": 30,
    "initial_capital": 1000
})
result = backtest.json()
print(f"ROI: {result['roi_pct']}%")
print(f"Win Rate: {result['win_rate_pct']}%")

if result['roi_pct'] > 5:  # Minimal 5% profit
    print("\n✅ Backtest passed! Moving to Paper Trading...")
    
    # 2. PAPER TRADING PHASE
    print("\nPhase 2: Paper Trading...")
    
    # Get current price
    price_response = requests.get(f"{BASE_URL}/api/toko/price/BTC/USDT")
    current_price = price_response.json()['current_price']
    
    # Calculate position size with risk management
    position = requests.post(f"{BASE_URL}/api/risk/position-size", json={
        "capital": 1000,
        "entry_price": current_price,
        "stop_loss_price": current_price * 0.97  # 3% stop loss
    })
    pos_size = position.json()
    print(f"Recommended size: {pos_size['position_value_usdt']} USDT")
    
    # Place paper buy
    buy = requests.post(f"{BASE_URL}/api/paper/buy", json={
        "symbol": "BTC/USDT",
        "amount_usdt": pos_size['position_value_usdt']
    })
    print(f"Buy result: {buy.json()}")
    
    # Monitor position (simulate)
    time.sleep(5)
    
    # Check account
    account = requests.get(f"{BASE_URL}/api/paper/account")
    print(f"\nAccount status: {account.json()}")
    
else:
    print("\n❌ Backtest failed! Strategy needs improvement.")
```

## 🛡️ Safety Checklist

Sebelum LIVE trading, pastikan:

- [ ] Backtest ROI > 5% selama 30+ hari
- [ ] Paper trading profit konsisten 1-2 minggu
- [ ] Win rate > 50%
- [ ] Max drawdown < 15%
- [ ] Tested dengan berbagai market condition
- [ ] Risk management limits sudah set
- [ ] Fee calculation sudah akurat
- [ ] Stop-loss & take-profit sudah tested

## 📈 Risk Management Rules

Bot otomatis enforce rules ini:

1. **Max Position Size:** 20% dari capital per trade
2. **Max Daily Loss:** 5% dari capital
3. **Max Drawdown:** 15% dari peak
4. **Max Open Positions:** 5 concurrent
5. **Risk per Trade:** 2% dari capital

Edit di `.env` untuk customize.

## 🚨 Common Pitfalls (Yang Sering Dilupakan)

### 1. Trading Fees
❌ **SALAH:** "Profit 1%, langsung untung!"
✅ **BENAR:** "Profit 1%, tapi fee 0.2%, net profit cuma 0.8%"

Bot sekarang otomatis hitung fee di setiap transaksi.

### 2. Slippage
❌ **SALAH:** "Buy at $50,000 pasti dapat $50,000"
✅ **BENAR:** "Buy at $50,000 bisa dapat $50,025 karena slippage"

Bot simulate slippage 0.05% (customizable).

### 3. Overfitting
❌ **SALAH:** "Backtest profit 1000%! Strategi sempurna!"
✅ **BENAR:** "Backtest harus test di berbagai periode, bukan 1 periode lucky"

Run batch backtest untuk validasi.

### 4. Position Sizing
❌ **SALAH:** "All-in setiap trade!"
✅ **BENAR:** "Risk 2% per trade, max 20% per position"

Use `risk_manager.calculate_position_size()`.

## 📚 Modules Documentation

### backtesting.py
```python
engine = BacktestEngine(initial_capital=1000)
result = await engine.run_backtest('BTC/USDT', timeframe='1h', days_back=30)
```

### paper_trading.py
```python
from paper_trading import paper_account

# Buy
result = paper_account.place_market_buy('BTC/USDT', 100, current_price)

# Sell
result = paper_account.place_market_sell('BTC/USDT', 100, current_price)
```

### fee_calculator.py
```python
from fee_calculator import get_calculator

calc = get_calculator('tokocrypto')
buy_cost = calc.calculate_buy_cost(100, 50000)
profit_target = calc.calculate_profit_target(50000, 0.002, 5)
```

### risk_manager.py
```python
from risk_manager import RiskManager

rm = RiskManager(initial_capital=1000)
position = rm.calculate_position_size(1000, 50000, 48500)
can_trade = rm.can_open_position(2, 1000, 150)
```

## 🐛 Troubleshooting

### "Module not found"
```bash
pip install -r requirements.txt
```

### "Database error"
```bash
python database.py  # Re-initialize
```

### "Exchange connection failed"
Check API keys di `.env` dan internet connection.

### "Paper trading not working"
```bash
# Reset paper account
curl -X POST http://localhost:8000/api/paper/reset \
  -H "Content-Type: application/json" \
  -d '{"balance": 1000}'
```

## 📞 Support

Jika ada error atau pertanyaan, cek:
1. File `sys_logger` untuk error logs
2. API response messages
3. Database untuk trade history

## ⚖️ License & Disclaimer

**DISCLAIMER:** Bot ini untuk educational purposes. Trading crypto berisiko tinggi. Developer tidak bertanggung jawab atas kerugian financial. Selalu test dengan paper trading dulu!

---

**Remember:** 
- ✅ BACKTEST dulu
- ✅ PAPER TRADING dulu
- ⚠️ LIVE trading terakhir (setelah proven profitable)

**Never trade with money you can't afford to lose!**
