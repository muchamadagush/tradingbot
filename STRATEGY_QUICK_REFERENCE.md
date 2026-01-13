# 🎯 QUICK REFERENCE: Trading Strategy

## 1️⃣ THE DECISION TREE

```
┌─ Check Market Condition ─┐
│                          │
├─ Calculate ADX (Trend)   │
├─ Calculate BB Width      │
│                          │
└─────────────┬────────────┘
              │
    ┌─────────┼─────────┐
    │         │         │
    ▼         ▼         ▼
[SQUEEZE]  [TREND]  [SIDEWAYS]
BB<8%     ADX>20     ADX<20
    │         │         │
    ▼         ▼         ▼
[BREAKOUT] [EMA]   [RSI]
Price>BB  9>21    <45→BUY
          RSI<75  >72→SELL

    │         │         │
    └────────┬┴─────────┘
             │
             ▼
        BUY / SELL / HOLD
             │
    ┌────────┴────────┐
    │                 │
    ▼                 ▼
  ENTER            CHECK
  TRADE           QUALITY
    │              │
    │         [Signal OK?]
    │              │
    └──────┬───────┘
           │
           ▼
       EXECUTE
        ORDER
```

---

## 2️⃣ THREE SUB-STRATEGIES EXPLAINED

### Strategy A: TREND FOLLOWING
**When:** ADX > 20 (Strong trend detected)
```
EMA9 ──────┐
           ├─ Uptrend? → BUY (if RSI < 75)
EMA21 ─────┘
           
Result: Catch 5-20% moves
Risk: Lag in turning points
```

### Strategy B: MEAN REVERSION
**When:** ADX < 20 (Sideways market)
```
RSI = 0───────┐
              ├─ Price bounces
RSI = 50──────┤ between support
              ├─ and resistance
RSI = 100─────┘

BUY when RSI < 45 (Oversold)
SELL when RSI > 72 (Overbought)
Result: 1-3% quick moves
Risk: Whipsaw in breakouts
```

### Strategy C: BREAKOUT
**When:** BB Width < 8% (Volatility squeeze)
```
        ┌─ Upper BB (Resistance)
        │
Squeeze │ Price compressed
        │ 
        └─ Lower BB (Support)

BREAK OUT? → BUY if RSI > 50
Result: Catch momentum after squeeze
Risk: False breakouts
```

---

## 3️⃣ ENTRY CONDITIONS (ALL MUST BE TRUE)

```
✅ Strategy Signal = BUY
   └─ From one of 3 sub-strategies above
   
✅ Signal Quality Pass
   └─ Win rate > 40% (self-learning)
   
✅ Multi-TF Confirm
   └─ 15-min trend ≠ Downtrend
   
✅ Spread Check
   └─ Bid-Ask spread < 0.5%
   
✅ Liquidity Check
   └─ Estimated slippage < 0.5%
   
✅ Risk Manager Pass
   └─ Open positions < Limit
   └─ Daily loss < Limit
   └─ Not in cooldown

>>> ALL PASS? ✅ EXECUTE BUY <<<
```

---

## 4️⃣ EXIT CONDITIONS (ANY ONE TRIGGERS EXIT)

```
┌─── TAKE PROFIT ───┐
│  Profit ≥ 1.5%   │ → EXIT ✅
└───────────────────┘

┌─── STOP LOSS ───┐
│  Loss ≥ 3%     │ → EXIT ❌
└────────────────┘

┌─── TRAILING STOP ───┐
│  (IF Profit ≥ 1%)  │
│  Profit drops 1.5% │ → EXIT ✅
└──────────────────────┘
```

**Trailing Stop Detail:**
```
Price: $100 → $101.50 (↑1.5%, Activate)
High:  $101.50
TS Level: $101.50 × (1 - 0.015) = $99.98

Price: $101.50 → $100.50 → $99.50
Last: $99.50 < $99.98
→ Trailing Stop HIT! EXIT.
```

---

## 5️⃣ REAL EXAMPLE: BITCOIN TRADE

```
Time: 12:00 - Price: $45,000

Step 1: Scan Indicators
├─ RSI(14) = 55 (Neutral)
├─ ADX = 25 (Trend starting)
├─ EMA9 = $44,980
├─ EMA21 = $44,900
└─ Conclusion: EMA9 > EMA21 → TREND

Step 2: Strategy Selected
└─ TREND_FOLLOWING (ADX > 20)

Step 3: Signal Check
├─ EMA9 ($44,980) > EMA21 ($44,900)? YES ✅
├─ RSI (55) < 75? YES ✅
└─ Signal: BUY ✅

Step 4: Quality & Confirmation
├─ TREND_FOLLOWING win rate: 52%? YES ✅
├─ 15m trend UP or NEUTRAL? UP ✅
├─ Spread < 0.5%? YES ✅
└─ Risk OK? YES ✅

Step 5: Execute
├─ Entry Price: $45,000
├─ Position Size: 0.1 BTC (based on ATR)
├─ Stop Loss: 3% = $43,650
├─ Take Profit: 1.5% = $45,675
└─ Trade OPENED ✅

Step 6: Monitoring (Every 2 sec)
Time 12:02 │ Price $45,100 │ Profit +$10 │ TS Activate: 1% hit
Time 12:04 │ Price $45,500 │ Profit +$50 │ Trail at $44,842
Time 12:06 │ Price $45,300 │ Profit +$30 │ Still trailing
Time 12:08 │ Price $44,850 │ Profit -$15 │ < Trail ($44,842)
           └─────────────────────────────────────────────
           TRAILING STOP HIT! SELL at $44,850

Result: +0.19% profit (after fees) ✅
```

---

## 6️⃣ VOLATILITY ADJUSTMENT

```
Normal Market (ATR = 2%):
├─ Entry Risk: 2% of portfolio
└─ Position: 0.1 BTC

Volatile Market (ATR = 4%):
├─ Volatility_Factor = 2/4 = 0.5x
├─ Entry Risk: 2% × 0.5 = 1% of portfolio
└─ Position: 0.05 BTC (SMALLER)
  └─ Reason: Protect against wider swings

Calm Market (ATR = 1%):
├─ Volatility_Factor = 2/1 = 2.0x
├─ Entry Risk: 2% × 2.0 = 4% of portfolio
└─ Position: 0.2 BTC (LARGER)
  └─ Reason: Agressive when risk low
```

---

## 7️⃣ KEY PARAMETERS (TUNABLE)

```
Entry RSI Thresholds:
├─ Oversold: < 45 (BUY signal)
└─ Overbought: > 72 (SELL signal)

Profit & Loss Targets:
├─ TP = 1.5% (0.015)
└─ SL = 3.0% (0.03)

Trailing Stop:
├─ Activation: 1% profit
└─ Distance: 1.5% behind high

Signal Quality:
├─ Min Win Rate: 40%
└─ Min Sample: 10 trades

Spread Tolerance:
├─ Max: 0.5%
└─ Skip if higher

Volatility:
├─ BB Width < 8%: BREAKOUT mode
└─ ADX > 20: TREND mode
```

---

## 8️⃣ BOT PROFILE: HUNTER

```
Tokocrypto Trading Bot
├─ Timeframe: 1-minute
├─ Trade Size: $12 per order
├─ Position Limit: 3 concurrent
├─ Risk/Trade: 3%
├─ Daily Loss Limit: 5%
├─ Cooldown: 2 hours after loss limit hit
│
└─ Loop Rate: Every 1 second
   ├─ Check existing trade (manage exit)
   └─ Or scan new opportunities
```

---

## 9️⃣ ADVANTAGE vs DISADVANTAGE

### ✅ ADVANTAGES:
1. **Adaptive** - Changes strategy based on market
2. **Self-Learning** - Tracks signal quality
3. **Risk-Aware** - Volatility-adjusted sizing
4. **Multi-Confirmation** - Reduces false signals
5. **Trailing Stop** - Catches big moves safely

### ⚠️ DISADVANTAGES:
1. **Lag** - EMA slower than price
2. **Whipsaws** - Wrong strategy chosen sometimes
3. **Parameter Sensitive** - Need tuning per coin/market
4. **Data Quality** - Exchange connection critical
5. **Slippage** - Real-world cost not always predictable

---

## 🔟 HOW TO INTERPRET LOGS

```
📊 Scanned 50 pairs, top 10 selected
  → Got tickers from exchange

✅ BTC/USDT | TREND_FOLLOWING | Uptrend & Healthy RSI | HTF:UP → BUY
  → Strategy selected, signal found, allowed

⏭️ Skip ETH/USDT: high spread 0.75%
  → Spread too wide, skip entry

🔄 Managing BTC/USDT
  → Trade open, monitoring price

📊 Trade closed: BTC/USDT | TRAILING_STOP | PnL: $1.50
  → Exit triggered by trailing stop

⏸️ Hunter in cooldown: 120s remaining
  → Risk limits hit, waiting before next trade

⛔ Trading blocked by kill switch
  → Manual override or weekly loss limit hit
```

---

## 📌 SUMMARY

This is a **Regime-Adaptive, Risk-Managed, Self-Learning** trading strategy:

1. **Regime Detection** → Choose strategy based on ADX + BB Width
2. **Signal Generation** → EMA, RSI, or Breakout based on regime
3. **Quality Filter** → Only trade if historical win rate > 40%
4. **Risk Control** → Position sizing by volatility, ATR-based stops
5. **Exit Rules** → TP 1.5%, SL 3%, Trailing Stop 1.5%
6. **Per-Bot Limits** → Hunter: 3 positions, 3% risk, 5% daily max loss

**Result:** Consistent, profitable, automated trading with human-like decision making.
