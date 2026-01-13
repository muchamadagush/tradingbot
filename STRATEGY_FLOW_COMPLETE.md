# 🔄 COMPLETE TRADING FLOW DIAGRAM

## FULL HUNTER BOT EXECUTION LOOP

```
╔════════════════════════════════════════════════════════════════════════════╗
║                         HUNTER BOT MAIN LOOP                              ║
║                      (Runs Every 1-2 Seconds)                             ║
╚════════════════════════════════════════════════════════════════════════════╝

                              START LOOP
                                  │
                                  ▼
                    ┌─────────────────────────┐
                    │  KILL SWITCH CHECK      │
                    │  Is trading allowed?    │
                    └────┬───────────────┬────┘
                         │               │
                        YES              NO
                         │               │
                         ▼               ▼
                     Continue      Set Status:
                                   ⛔ KILL SWITCH
                                   └─ Sleep 30s
                                      Loop again


                    ┌─────────────────────────────────┐
                    │  RISK MANAGER CHECK             │
                    │  Can trade new position?        │
                    │  • Open positions < 3?          │
                    │  • Daily PnL > -5%?             │
                    │  • Not in 2h cooldown?          │
                    └────┬──────────────────────┬─────┘
                         │                      │
                        YES                     NO
                         │                      │
                         ▼                      ▼
                     Continue             Set Status:
                                          ⚠️ RISK LIMIT
                                          └─ Sleep 30s


        ┌───────────────────────────────────────────────────────────┐
        │                                                           │
        ▼                                                           │
    ┌─────────────────────────────────────────────────────────┐   │
    │  DO WE HAVE OPEN TRADE?                                 │   │
    │  (Check database: status = 'OPEN')                       │   │
    └──┬─────────────────────────────────────┬────────────────┘   │
       │                                       │                    │
      YES                                     NO                    │
       │                                       │                    │
       ▼                                       ▼                    │
    ┌──────────────────────────┐        ┌──────────────────┐       │
    │  MANAGE OPEN POSITION    │        │  SCAN NEW OPTY   │       │
    │  (Exit Decision)         │        │  (Entry Decision)│       │
    └──┬───────────────────────┘        └────┬─────────────┘       │
       │                                     │                      │
       │ • Fetch ticker                      │ • Get top liquid     │
       │ • Calculate PnL%                    │   coins              │
       │ • Check TP (1.5%)                   │                      │
       │ • Check SL (3%)                     │ FOR EACH SYMBOL:     │
       │ • Check Trailing Stop               │ ├─ Check spread      │
       │                                     │ ├─ Analyze signal    │
       ▼                                     │ ├─ Check liquidity   │
    ┌─────────────────────┐                 │ ├─ Signal = BUY?     │
    │ Exit Condition Met? │                 │ └─ Execute if OK     │
    └────┬────────┬───────┘                 │                      │
         │        │                         │                      │
        YES      NO                         │                      │
         │        │                         │                      │
         ▼        ▼                         ▼                      │
       CLOSE    HOLD          ┌──────────────────────────────────┐ │
       TRADE   POSITION       │  FOR EACH TOP LIQUID COIN        │ │
         │        │           │  (e.g., BTC/USDT, ETH/USDT...)  │ │
         │        │           └────┬─────────────────────────────┘ │
         │        │                │                               │
         │        │                ▼                               │
         │        │        ┌──────────────────────┐               │
         │        │        │ Step 1: Check Spread │               │
         │        │        │ Bid-Ask % < 0.5%?   │               │
         │        │        └────┬──────────┬──────┘               │
         │        │             │          │                       │
         │        │            YES        NO                       │
         │        │             │          │                       │
         │        │             ▼          ▼                       │
         │        │        Continue     Skip Coin                 │
         │        │             │        │ │                       │
         │        │             │        │ │                       │
         │        │             ▼        └─┼─ Sleep 1s            │
         │        │        ┌──────────────────────────┐            │
         │        │        │ Step 2: Analyze Market  │            │
         │        │        │ • Fetch 100x 1m candles │            │
         │        │        │ • Calculate indicators  │            │
         │        │        │ • decide_strategy()     │            │
         │        │        │ • Returns: ACTION       │            │
         │        │        └────┬────────────┬───────┘            │
         │        │             │            │                     │
         │        │            BUY        HOLD/SELL               │
         │        │             │            │                     │
         │        │             ▼            ▼                     │
         │        │        ┌──────────────┐ Skip Coin             │
         │        │        │Step 3:       │ │                      │
         │        │        │Check Quality │ │                      │
         │        │        │ Win rate >40%│ │                      │
         │        │        └────┬──┬──────┘ │                      │
         │        │             │  │        │                      │
         │        │            OK FAIL      │                      │
         │        │             │  │        │                      │
         │        │             ▼  ▼        │                      │
         │        │        Continue Skip    │                      │
         │        │             │  │        │                      │
         │        │             ▼  │        │                      │
         │        │        ┌──────────────┐ │                      │
         │        │        │Step 4:       │ │                      │
         │        │        │Multi-TF CFM  │ │                      │
         │        │        │ 15m ≠ Down?  │ │                      │
         │        │        └────┬──┬──────┘ │                      │
         │        │             │  │        │                      │
         │        │            OK FAIL      │                      │
         │        │             │  │        │                      │
         │        │             ▼  │        │                      │
         │        │        ┌──────────────┐ │                      │
         │        │        │Step 5:       │ │                      │
         │        │        │Check Liquid  │ │                      │
         │        │        │Slippage <0.5%│ │                      │
         │        │        └────┬──┬──────┘ │                      │
         │        │             │  │        │                      │
         │        │            OK FAIL      │                      │
         │        │             │  │        │                      │
         │        │             ▼  │        │                      │
         │        │        ┌──────────────┐ │                      │
         │        │        │Step 6:       │ │                      │
         │        │        │Execute BUY   │ │                      │
         │        │        │ • Fetch price│ │                      │
         │        │        │ • Send order │ │                      │
         │        │        │ • Log trade  │ │                      │
         │        │        │ • Break scan │ │                      │
         │        │        └────┬──┬──────┘ │                      │
         │        │             │  │        │                      │
         │        │            OK FAIL      │                      │
         │        │             │  │        │                      │
         │        │             ▼  └────────┘                      │
         │        │          Trade    Sleep 1s                     │
         │        │          Opened   → Next coin                  │
         │        │          │                                     │
         └────────┼──────────┘                                     │
                  │                                                │
                  ▼                                                │
            ┌──────────────┐                                       │
            │ SLEEP 1-2 sec│                                       │
            └────┬─────────┘                                       │
                 │                                                 │
                 └───────────────────────────────────────────┬────┘
                                                             │
                                                    LOOP AGAIN
```

---

## DETAILED: STRATEGY DECISION TREE

```
┌──────────────────────────────────────────────────────────────────┐
│                    MARKET ANALYSIS (1m)                          │
│                                                                  │
│  Fetch 100 candles → Calculate Indicators                       │
│  ├─ RSI(14) ──────────────────────┐                            │
│  ├─ MACD(12,26,9) ────────────────┤                            │
│  ├─ Bollinger Bands(20,2) ────────┼─→ decide_strategy()        │
│  ├─ ADX(14) ───────────────────────┤                            │
│  └─ EMA(9,21) ────────────────────┘                            │
└──────────────────────────────────────────────────────────────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │  Calculate Metrics   │
                  │                      │
                  │ ADX = 25 (trend?)    │
                  │ BB_Width = 7.5%      │
                  │ (wide or narrow?)    │
                  └──────┬───────┬──────┘
                         │       │
            ┌────────────┼─────┬─┴────────┐
            │            │     │          │
            ▼            ▼     ▼          ▼
        [SQUEEZE]   [TREND]  [WEAK]   [N/A]
        BB<8%       ADX>20   ADX<20
            │            │     │
            ▼            ▼     ▼
    ┌──────────────┐ ┌─────────────┐ ┌──────────────┐
    │ BREAKOUT     │ │ TREND       │ │ MEAN         │
    │ STRATEGY     │ │ FOLLOWING   │ │ REVERSION    │
    └──┬───────────┘ └──┬──────────┘ └──┬───────────┘
       │                │                │
       │ Logic:         │ Logic:         │ Logic:
       │                │                │
       ▼                ▼                ▼
    ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
    │Price > BBUp? │  │EMA9 > EMA21? │  │RSI < 45?     │
    │RSI > 50?     │  │RSI < 75?     │  │→ BUY         │
    │→ BUY         │  │→ BUY         │  │              │
    │              │  │              │  │RSI > 72?     │
    │Price<BBLow?  │  │EMA9 < EMA21? │  │→ SELL        │
    │→ SELL        │  │→ SELL (Death │  │              │
    │              │  │ Cross)       │  │ELSE → HOLD   │
    │ELSE → HOLD   │  │              │  │              │
    │ (Wait break) │  │ELSE → HOLD   │  └──────────────┘
    └──┬───────────┘  └──┬───────────┘
       │                 │
       └────────┬────────┘
                │
                ▼
        ┌──────────────┐
        │   Signal     │
        │  BUY/SELL    │
        │   /HOLD      │
        └──┬───────────┘
           │
           ▼
    ┌─────────────────────┐
    │ Quality Check (P4)  │
    │ Win Rate > 40%?     │
    └────┬───────┬────────┘
         │       │
        OK      FAIL
         │       │
         ▼       ▼
      Keep   Change to
      Signal  HOLD
         │       │
         └───┬───┘
             │
             ▼
    ┌─────────────────────┐
    │ Multi-TF Check (P4) │
    │ 15m Trend check     │
    │ DOWN? Block BUY     │
    └────┬───────┬────────┘
         │       │
        OK      BLOCKED
         │       │
         ▼       ▼
      Keep    Change to
      Signal   HOLD
         │       │
         └───┬───┘
             │
             ▼
     FINAL SIGNAL
    (BUY/SELL/HOLD)
```

---

## EXIT LOGIC: POSITION MANAGEMENT

```
                    OPEN TRADE
                      │
         ┌────────────┴────────────┐
         │                         │
         ▼                         ▼
    Fetch Ticker             Initialize/Update
    Calculate PnL%           Trailing Stop State
         │                         │
         ▼                         ▼
    ┌────────────────────┐   ┌──────────────────┐
    │ Check TP/SL/TS     │   │ Track high price │
    │                    │   │ (for trailing)   │
    └────┬────┬───┬──────┘   └────┬─────────────┘
         │    │   │               │
         ▼    ▼   ▼               ▼
    TP   SL   TS  Continue    ┌─────────────┐
    Hit  Hit  Hit  Monitoring │Price Update │
    1.5% 3%  -1.5%            └──┬──────────┘
     │    │   │                  │
     ▼    ▼   ▼    ┌─────────┬───┴───────┐
     CLOSE │   │    │         │           │
            │   │    ▼         ▼           ▼
            │   │  Price    Price      Price
            │   │  ↑        Flat       ↓
            │   │  │        │          │
            │   │  ▼        ▼          ▼
            │   │ Update  Check TS   Close if
            │   │ High    Trigger    < TS Level
            │   │         │
            │   │         ▼
            │   │      If Close
            │   │      < (High × 0.985)
            │   │         │
            │   │         ▼
            │   │      CLOSE
            │   │      (TS Hit)
            │   │
            ▼   ▼
          CLOSE (Exit)
            │
            ▼
      Log Trade
      Update Risk Manager
      Sleep 2 sec
```

---

## RISK MANAGEMENT INTEGRATION

```
┌────────────────────────────────────────────────┐
│          HUNTER BOT RISK PROFILE               │
└────────────────────────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
    ┌─────────┐  ┌──────┐   ┌──────────┐
    │Position │  │Daily │   │Cooldown  │
    │Limits   │  │Limits│   │System    │
    └────┬────┘  └──┬───┘   └────┬─────┘
         │          │            │
    Max 3 open  Max 5% loss   2 hour wait
    concurrent  per day       when limit hit
         │          │            │
         └──────┬───┴────────┬───┘
                │            │
         ┌──────▼────────────▼──────┐
         │ Before Every NEW Trade:  │
         │                          │
         │ 1. Can trade new?        │
         │    • Open pos < 3?  ✓    │
         │    • Daily PnL > -5%? ✓  │
         │    • Cooldown ended? ✓   │
         │                          │
         │ 2. Position size by ATR  │
         │    • Volatile→Smaller    │
         │    • Calm→Larger         │
         │                          │
         │ 3. Risk: 3% per trade    │
         │    • Stop: 3 × ATR       │
         │                          │
         │ 4. Position sizing:      │
         │    Size = Risk / SL_dist │
         └──────────────────────────┘
```

---

## SIGNAL QUALITY TRACKING (P4)

```
Every Trade Closes:
        │
        ▼
    ┌─────────────────────┐
    │ Record Outcome      │
    │ Strategy: TREND     │
    │ Signal: BUY         │
    │ PnL: +$2.50         │
    └──────┬──────────────┘
           │
           ▼
    ┌──────────────────────┐
    │ Update Win Rate      │
    │                      │
    │ TREND signals:       │
    │ Total: 15            │
    │ Wins: 8              │
    │ Win Rate: 53.3%      │
    └──────┬───────────────┘
           │
           ▼
    ┌──────────────────────┐
    │ Next Time TREND      │
    │ Signal Generated:    │
    │                      │
    │ Quality OK?          │
    │ (53.3% > 40%)        │
    │ YES ✓                │
    │ → Allow Entry        │
    └──────────────────────┘

If Win Rate drops below 40%:
    HOLD (Block entry) until
    Win rate improves again
```

---

## COMPLETE CYCLE TIME

```
Per Loop Iteration:

1. Kill Switch Check          ~0.1s
2. Risk Check                 ~0.1s
3. Manage Position (if open)  ~2-5s
   └─ Fetch ticker
   └─ Calculate PnL
   └─ Check conditions

4. OR Scan New (if no open)   ~1-3s per coin
   └─ Get tickers (all coins)
   └─ Filter by spread
   └─ Analyze signals
   └─ Check quality
   └─ Multi-TF confirm
   └─ Check liquidity
   └─ Execute if all OK

5. Sleep                      1-2s

TOTAL PER LOOP: 3-8 seconds

Hunter scans top 10 coins continuously,
typically finds 1-2 BUY signals per hour.
Holds positions for 2-10 minutes on average.
```

---

## PARAMETER SUMMARY

```
═══════════════════════════════════════════════════
STRATEGY PARAMETERS
═══════════════════════════════════════════════════

INDICATORS:
├─ RSI Period: 14
├─ MACD: 12/26/9
├─ Bollinger: 20 period, 2 STD
├─ ADX: 14 period
└─ EMA: 9/21

DECISION THRESHOLDS:
├─ Squeeze (Breakout): BB Width < 8%
├─ Trend (EMA): ADX > 20
├─ Sideways (RSI): ADX ≤ 20
├─ RSI Oversold: < 45 (BUY)
├─ RSI Overbought: > 72 (SELL)
├─ EMA Filter: RSI < 75 before BUY
├─ Breakout: RSI > 50 confirmation
└─ Multi-TF: 15m must not be DOWN

EXIT RULES:
├─ Take Profit: 1.5%
├─ Stop Loss: 3%
├─ Trailing Stop Activation: 1%
└─ Trailing Stop Distance: 1.5%

RISK LIMITS (Hunter):
├─ Max Positions: 3
├─ Risk per Trade: 3%
├─ Daily Loss Limit: 5%
├─ Cooldown: 2 hours
└─ Volatility Factor: 0.5x - 2.0x

QUALITY FILTER (P4):
├─ Min Win Rate: 40%
├─ Min Samples: 10
└─ Lookback: Last 100 signals

SIGNAL QUALITY:
├─ Spread Check: < 0.5%
├─ Liquidity: Slippage < 0.5%
└─ Multi-TF: 15m confirmation

═══════════════════════════════════════════════════
```

---

## KEY DECISION POINTS

```
┌─────────────────────────────────────────┐
│  IF → THEN (Decision Tree)              │
└─────────────────────────────────────────┘

1. ADX > 20 AND EMA9 > EMA21
   ├─ AND RSI < 75
   └─ → TREND BUY SIGNAL ✓

2. ADX > 20 AND EMA9 < EMA21
   → TREND SELL SIGNAL ✓

3. ADX < 20 AND RSI < 45
   → MEAN_REV BUY SIGNAL ✓

4. ADX < 20 AND RSI > 72
   → MEAN_REV SELL SIGNAL ✓

5. BB Width < 8% AND Price > BBUp
   ├─ AND RSI > 50
   └─ → BREAKOUT BUY SIGNAL ✓

6. BB Width < 8% AND Price < BBLow
   → BREAKOUT SELL SIGNAL ✓

7. ALL conditions met
   ├─ Signal quality OK
   ├─ Multi-TF OK
   ├─ Spread OK
   ├─ Liquidity OK
   └─ → EXECUTE ORDER ✓

8. Price ≥ Entry + 1.5%
   → TAKE PROFIT ✓

9. Price ≤ Entry - 3%
   → STOP LOSS ✓

10. Price ≤ (High × 0.985)
    ├─ AND Profit ≥ 1%
    └─ → TRAILING STOP ✓
```

This is the complete automated decision-making system! 🎯
