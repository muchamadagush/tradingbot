# ==========================================
# File: strategies/solana_trader.py
# ==========================================

import time
import pandas as pd
import pandas_ta as ta

from strategies.base import BaseStrategy


class SolanaTraderStrategy(BaseStrategy):
    """
    Momentum + Volume Breakout Strategy
    Designed for Solana memecoins
    """

    name = "SOLANA_TRADER"

    # ---- CONFIG ----
    MIN_CANDLES = 40
    COOLDOWN_SECONDS = 15 * 60
    MAX_HOLD_SECONDS = 20 * 60

    HARD_SL_PCT = -12.0
    TP1_PCT = 20.0
    TP2_PCT = 30.0

    def __init__(self):
        self.last_entry_ts = {}

    # ==================================================
    # BUY LOGIC
    # ==================================================

    def should_buy(self, market) -> (bool, str):

        df: pd.DataFrame = market.get("df")
        token = market.get("token", "BACKTEST")

        if df is None or len(df) < self.MIN_CANDLES:
            return False, "not enough candles"

        # ---- COOLDOWN (LIVE ONLY) ----
        last_entry = self.last_entry_ts.get(token)
        if last_entry and time.time() - last_entry < self.COOLDOWN_SECONDS:
            return False, "cooldown active"

        df = df.copy()

        # ==================================================
        # INDICATORS
        # ==================================================

        df["rsi"] = ta.rsi(df["close"], length=14)
        df["ema20"] = ta.ema(df["close"], length=20)
        df["ema50"] = ta.ema(df["close"], length=50)
        df["atr"] = ta.atr(df["high"], df["low"], df["close"], length=14)

        bb = ta.bbands(df["close"], length=20, std=2)
        bb_l = next(c for c in bb.columns if c.startswith("BBL"))
        bb_u = next(c for c in bb.columns if c.startswith("BBU"))

        df["bb_l"] = bb[bb_l]
        df["bb_u"] = bb[bb_u]

        # ==================================================
        # 🔥 CRITICAL FIX: DROP NaN WARM-UP ROWS
        # ==================================================

        df.dropna(inplace=True)

        if len(df) < 5:
            return False, "indicator warmup"

        last = df.iloc[-1]

        # ==================================================
        # MARKET REGIME FILTER
        # ==================================================

        # 1. Trend
        if last["ema20"] <= last["ema50"]:
            return False, "no uptrend"

        # 2. Volatility expansion
        atr_ma = df["atr"].rolling(20).mean().iloc[-1]
        if last["atr"] <= atr_ma:
            return False, "low volatility"

        # 3. Bollinger expansion
        bb_width = (last["bb_u"] - last["bb_l"]) / last["close"]
        if bb_width < 0.05:
            return False, "bb too narrow"

        # ==================================================
        # ENTRY SIGNAL
        # ==================================================

        if not (45 < last["rsi"] < 70):
            return False, "rsi not in momentum zone"

        vol_ma = df["volume"].rolling(20).mean().iloc[-1]
        if last["volume"] <= vol_ma:
            return False, "no volume expansion"

        return True, "momentum breakout confirmed"

    # ==================================================
    # SELL LOGIC
    # ==================================================

    def should_sell(self, position, market) -> (bool, str):

        pnl = position.get("pnl_pct", 0.0)

        if pnl <= self.HARD_SL_PCT:
            return True, f"hard SL hit ({pnl:.2f}%)"

        if pnl >= self.TP1_PCT and not position.get("tp1_hit", False):
            position["tp1_hit"] = True
            return True, "tp1 partial"

        if pnl >= self.TP2_PCT:
            return True, "tp2 full exit"

        return False, ""

    # ==================================================
    # STATE
    # ==================================================

    def on_buy(self, position):
        token = position.get("token", "BACKTEST")
        self.last_entry_ts[token] = time.time()
        position["tp1_hit"] = False

    def on_sell(self, position):
        pass
