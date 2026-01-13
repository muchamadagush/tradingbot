# 📊 Strategi Trading - Penjelasan Detail

## Overview
TradingBot menggunakan **Meta Strategy Adaptif (Harmonic Strategy Switcher)** yang menggabungkan 3 sub-strategi berbeda dan memilih yang paling sesuai dengan kondisi pasar real-time.

---

## 🎯 ARSITEKTUR STRATEGI

### 1. **Indikator Teknis (Fundamental)**
```
┌─────────────────────────────────────────────┐
│         OHLCV Data (1-menit)                │
│    [Open, High, Low, Close, Volume]         │
└────────────────┬────────────────────────────┘
                 │
         ┌───────▼────────┐
         │ populate_      │
         │ indicators()   │
         └───────┬────────┘
                 │
    ┌────┬─────┬─┴─┬─────┬──────┐
    │    │     │   │     │      │
    ▼    ▼     ▼   ▼     ▼      ▼
   RSI  MACD  BBands ADX  ATR   EMA
   14    12/26/9   20    14     9/21
```

**Indikator yang Digunakan:**
1. **RSI (14)** - Momentum, Range: 0-100
   - RSI < 45 → Oversold (Beli)
   - RSI 45-72 → Neutral
   - RSI > 72 → Overbought (Jual)

2. **MACD (12/26/9)** - Trend Momentum
   - MACD > Signal Line → Bullish
   - MACD < Signal Line → Bearish

3. **Bollinger Bands (20,2)** - Volatility & Breakout
   - Price > Upper BB → Breakout Up
   - Price < Lower BB → Breakdown Down
   - BB Width = (Upper - Lower) / Close

4. **ADX (14)** - Trend Strength
   - ADX < 20 → Weak/Sideways
   - ADX 20-40 → Trending
   - ADX > 40 → Strong Trend

5. **ATR (14)** - Volatility Measurement
   - Digunakan untuk stop loss sizing (P4)
   - ATR% = (ATR / Close) × 100

6. **EMA (9/21)** - Trend Direction
   - EMA9 > EMA21 → Uptrend
   - EMA9 < EMA21 → Downtrend

---

## 🔄 CORE LOGIC: META STRATEGY SWITCHER

Bot memilih strategi berdasarkan **kondisi pasar (ADX + BB Width)**:

```python
if BB_Width < 8%:
    ├─ MODE: BREAKOUT (Volatility Squeeze)
    └─ Cari ledakan setelah periode keseimbangan
    
elif ADX > 20:
    ├─ MODE: TREND FOLLOWING (Clear Trend)
    └─ Follow EMA crossover dengan filter RSI
    
else:
    ├─ MODE: MEAN REVERSION (Sideways)
    └─ Jual saat Overbought, Beli saat Oversold
```

---

## 📈 SUB-STRATEGI #1: TREND FOLLOWING (ADX > 20)

**Kondisi:** Trend terlihat jelas (ADX strength)

**Logic:**
```
EMA9 > EMA21 ?
├─ YES → BUY Signal
│   └─ Syarat tambahan: RSI < 75 (Jangan beli di puncak)
│   └─ Alasan: Hindari squeeze/pullback setelah kenaikan brutal
│
└─ NO → EMA9 < EMA21
    └─ SELL Signal (Death Cross)
    └─ Trend sudah berakhir, kemungkinan downtrend
```

**Keuntungan:**
- Catch big trend moves
- Reduce whipsaws di trending market

**Kelemahan:**
- Lag (EMA slowly follow price)
- Bad di choppy/sideways market

---

## 🔄 SUB-STRATEGI #2: MEAN REVERSION (ADX ≤ 20)

**Kondisi:** Sideways/choppy market, no clear trend

**Logic:**
```
RSI Oversold (< 45) ?
├─ YES → BUY Signal
│   └─ Price mencapai support area
│
RSI Overbought (> 72) ?
├─ YES → SELL Signal
│   └─ Price mencapai resistance area
│   └─ PENTING: Threshold 72 (bukan 55)
│       Alasan: Mencegah jual terlalu cepat saat early breakout
│
ELSE → HOLD
    └─ RSI masih neutral (45-72)
```

**Keuntungan:**
- Profitable di sideways market
- Quick entry/exit

**Kelemahan:**
- Whipsaw dalam trending market
- Jebakan: false breakouts

---

## 💥 SUB-STRATEGI #3: BREAKOUT (BB Width < 8%)

**Kondisi:** Volatility Squeeze (terlihat keseimbangan)

**Logic:**
```
Price > Upper Bollinger Band ?
├─ AND RSI > 50 (Momentum support)
├─ YES → BUY Signal (Valid Breakout Up)
│   └─ Price melampaui resistance
│   └─ Didukung momentum bullish
│
Price < Lower Bollinger Band ?
├─ YES → SELL Signal (Breakdown Down)
│   └─ Price memecah support
│
ELSE → HOLD (Inside Squeeze)
    └─ Tunggu ledakan
```

**Keuntungan:**
- Entry saat volatility akan meledak
- Big move potential setelah squeeze

**Kelemahan:**
- False breakout (trap)
- Timing sensitive

---

## ⚡ ENHANCEMENT: SIGNAL QUALITY FILTER (P4)

**Apa:** Sistem tracking untuk setiap sub-strategy

**Cara Kerja:**
```
1. Setiap trade dicatat dengan outcomes:
   ├─ Signal yang dihasilkan (BUY/SELL)
   ├─ Profit/Loss hasil trade
   └─ Strategy yang digunakan

2. Hitung win rate per strategy:
   └─ Win Rate = (Winning Trades / Total Trades) × 100%

3. Quality Check sebelum entry:
   └─ if Win Rate < 40% and Sample > 10:
       └─ BLOCK signal (HOLD instead)
```

**Default Threshold:** 40% win rate minimum

**Benefit:**
- Avoid low-quality signals
- Adapt ke market condition
- Self-learning bot

---

## 🔗 MULTI-TIMEFRAME CONFIRMATION (P4)

**Purpose:** Confirmation bias reduction + Trend alignment

**Logic:**
```
BUY Signal di 1m chart?
├─ Check 15m chart trend
├─ if 15m trend = UP or NEUTRAL
│   └─ ✅ Allow BUY
└─ if 15m trend = DOWN
    └─ ❌ BLOCK (HOLD)
    └─ Alasan: Jangan fight higher timeframe
```

**Keuntungan:**
- Entry aligned dengan bigger picture
- Reduce counter-trend trades

---

## 📏 VOLATILITY-ADJUSTED POSITION SIZING (P4)

**Konsep:** Position size adjust berdasarkan market volatility

```
Position Size = Risk Amount / Risk Per Unit

Where:
├─ Risk Amount = Portfolio × (Risk% × Volatility_Factor)
├─ Volatility_Factor = Normal_ATR / Current_ATR
│   └─ High ATR (volatile) → Small position
│   └─ Low ATR (calm) → Large position
│
└─ Stop Price = Entry × (1 - ATR% × 1.5)
    └─ Stop loss jarak = 1.5x ATR (dynamic)
```

**Example:**
```
Portfolio: $1000
Base Risk: 2%
Normal ATR: 2%

Case 1 - Volatile Market (ATR = 4%)
├─ Volatility_Factor = 2/4 = 0.5x
├─ Risk = $1000 × 2% × 0.5 = $10
└─ Position: Smaller (safer)

Case 2 - Calm Market (ATR = 1%)
├─ Volatility_Factor = 2/1 = 2.0x (capped at 2.0)
├─ Risk = $1000 × 2% × 2.0 = $40
└─ Position: Larger (aggressive)
```

---

## 🛑 ENTRY & EXIT RULES

### ENTRY Checklist:
```
1. ✅ Strategy signal = BUY
2. ✅ Spread check: Bid-Ask < 0.5% (P3)
3. ✅ Liquidity check: Slippage < 0.5% (P3)
4. ✅ Signal quality: Win rate > 40% (P4)
5. ✅ Multi-TF confirm: 15m not in downtrend (P4)
6. ✅ Risk check: Open positions < Max allowed
```

### EXIT Rules:
```
TAKE PROFIT (TP):
├─ Profit ≥ 1.5% (TP = 0.015)
└─ Close IMMEDIATELY

STOP LOSS (SL):
├─ Loss ≥ 3% (SL = 0.03)
└─ Close IMMEDIATELY

TRAILING STOP (Hunter Bot):
├─ Aktivasi: Profit ≥ 1% (TRAILING_STOP_ACTIVATION_PCT = 0.01)
├─ Distance: 1.5% di bawah high (TRAILING_STOP_DISTANCE_PCT = 0.015)
│   └─ Jika price kembali turun 1.5%, jual
└─ Benefit: Capture upside dengan protected downside
```

**Flow Chart:**
```
Trade Open
    │
    ├─ Monitor Price
    │
    ├─ Price naik?
    │  └─ Update high watermark
    │     └─ Jika profit >= 1%: Aktifkan trailing stop
    │        └─ Jika price turun 1.5%: EXIT (Trailing Stop Hit)
    │
    ├─ Profit >= 1.5%?
    │  └─ YES → EXIT (TP Hit) ✅
    │
    └─ Loss >= 3%?
       └─ YES → EXIT (SL Hit) ❌
```

---

## 🤖 HUNTER BOT: FULL FLOW

```
Loop setiap detik:

┌─────────────────────────────────────────────────┐
│ 1. Check Kill Switch & Risk Limits              │
├─────────────────────────────────────────────────┤
│   ├─ Is trading allowed? (Kill Switch)          │
│   └─ Can trade new? (Risk Manager)              │
│       └─ if NO → Sleep 30s, skip                │
└─────────────────────────────────────────────────┘
                    │
         ┌──────────▼──────────┐
         │ Open Position?      │
         └────┬─────────┬──────┘
              │         │
             YES       NO
              │         │
    ┌─────────▼──┐    ┌─▼──────────────┐
    │   MANAGE   │    │  SCAN NEW      │
    │ OPEN TRADE │    │  OPPORTUNITY   │
    └────────────┘    └────────────────┘
         │                    │
         │        ┌───────────┼───────────┐
         │        │           │           │
         ▼        ▼           ▼           ▼
      Check   Get Top    Check Spread  Check
      Price   Coins       & Liquidity   Signal
         │        │           │           │
         │        └─────┬─────┘───────┬──┘
         │              │             │
         │              │      ┌──────▼──────┐
         │              └──────┤ Signal=BUY? │
         │                     └──┬─────┬────┘
         │                       YES   NO
         │                        │    │
    ┌────┴────────┐      ┌───────▼─┐  │
    │ Manage Exit │      │ Execute │  │
    │ (TP/SL/TS)  │      │  Order  │  │
    │             │      └───────┬─┘  │
    │ TP/SL Hit?  │              │    │
    │ └─ Close    │          Sleep 1s │
    │             │              │    │
    └────────┬────┘              │    │
             │                   │    │
             └───────┬───────────┘    │
                     │                │
                  Sleep 2s       Sleep 1s
                     │                │
                     └────────┬───────┘
                              │
                         Loop Again
```

---

## 💡 TRADING DECISIONS SUMMARY

| Market Condition | ADX | BB Width | Strategy | Entry Signal | Exit |
|---|---|---|---|---|---|
| Strong Uptrend | >40 | Any | TREND | EMA9>EMA21 & RSI<75 | TP/SL/TS |
| Weak Uptrend | 20-40 | Any | TREND | EMA9>EMA21 & RSI<75 | TP/SL/TS |
| Squeeze (Bullish) | <20 | <8% | BREAKOUT | Price>BBUp & RSI>50 | TP/SL/TS |
| Squeeze (Bearish) | <20 | <8% | BREAKOUT | Price<BBLow | TP/SL |
| Sideways | <20 | >8% | MEAN_REV | RSI<45 | TP/SL |
| Overbought | Any | Any | MEAN_REV | N/A (Sell) | SL |

---

## ⚙️ RISK MANAGEMENT INTEGRATION

### Per-Bot Risk Profiles (P1):

| Bot | Max Positions | Risk/Trade | Max Daily Loss | Cooldown |
|---|---|---|---|---|
| **HUNTER** | 3 | 3% | 5% | 2 hours |
| **TRADER** | 3 | 4% | 8% | 1 hour |
| **SNIPER** | 1 | 2% | 3% | 4 hours |

### Kill Switch (P0):
- Manual override: Stop all trading
- Auto trigger: Weekly loss > 15% portfolio

---

## 📊 SIGNAL QUALITY METRICS

Tracked metrics untuk optimization:
```
Per Strategy Win Rate:
├─ TREND_FOLLOWING: X% (from last 100 signals)
├─ MEAN_REVERSION: Y% (from last 100 signals)
└─ BREAKOUT: Z% (from last 100 signals)

Minimum acceptable: 40% (else blocked)
Recommendation: 50%+ untuk consistent profit
```

---

## 🔮 FUTURE OPTIMIZATIONS

1. **Machine Learning Integration**
   - Learn optimal RSI thresholds
   - Adaptive BB width threshold

2. **Correlation Analysis**
   - Avoid correlated pairs
   - Reduce risk in sector downturn

3. **Volume Profile**
   - Entry at volume support
   - Confirm breakout dengan volume spike

4. **News/Sentiment Filter**
   - Block trading saat major news
   - Avoid gap risk

---

## 📝 CONCLUSION

**Strategi ini adalah:**
- ✅ **Adaptif** - Switches based on market condition
- ✅ **Risk-Aware** - Volatility-adjusted sizing
- ✅ **Self-Learning** - Signal quality filtering
- ✅ **Multi-Confirmation** - Cross-timeframe + quality checks
- ✅ **Profitable** - Tested win-rate thresholds

**Best untuk:** Short-term swing trading (1-60 min), multi-asset scanning dengan automated risk management.
