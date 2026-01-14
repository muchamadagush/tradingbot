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

    # Risk-adjusted TP/SL (max 3 positions = 24% max portfolio loss)
    HARD_SL_PCT = -8.0       # Reduced from -12% to limit losses
    TP1_PCT = 15.0           # Reduced from 20% (ratio 1.875:1)
    TP2_PCT = 25.0           # Reduced from 30%
    
    # Dynamic SL based on ATR
    ATR_SL_MULTIPLIER = 2.0  # SL = entry - (ATR * multiplier)

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
        
        # ---- DYNAMIC ATR-BASED SL ----
        dynamic_sl_pct = position.get("dynamic_sl_pct", self.HARD_SL_PCT)
        
        # Use the tighter of hard SL or dynamic SL
        effective_sl = max(dynamic_sl_pct, self.HARD_SL_PCT)  # Both negative, max = less negative = tighter

        if pnl <= effective_sl:
            return True, f"SL hit ({pnl:.2f}% <= {effective_sl:.2f}%)"

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
        
        # Calculate dynamic SL based on ATR at entry
        atr = position.get("atr", 0)
        entry_price = position.get("entry_price", 0)
        
        if atr > 0 and entry_price > 0:
            # SL distance = ATR * multiplier
            sl_distance = atr * self.ATR_SL_MULTIPLIER
            dynamic_sl_pct = -(sl_distance / entry_price) * 100
            # Clamp to hard SL (don't allow wider than hard SL)
            position["dynamic_sl_pct"] = max(dynamic_sl_pct, self.HARD_SL_PCT)
        else:
            position["dynamic_sl_pct"] = self.HARD_SL_PCT

    def on_sell(self, position):
        pass

    # ==================================================
    # RISK-ADJUSTED POSITION SIZING
    # ==================================================

    def calculate_position_size(
        self, 
        capital: float, 
        entry_price: float, 
        atr: float,
        risk_pct: float = 2.0  # Default from RISK_PER_TRADE_PCT
    ) -> dict:
        """
        Calculate position size based on ATR and risk per trade.
        
        Args:
            capital: Available capital in USD
            entry_price: Entry price per unit
            atr: Current ATR value
            risk_pct: % of capital to risk per trade (from env/risk_manager)
            
        Returns:
            dict with position_size, sl_price, risk_amount
        """
        if atr <= 0 or entry_price <= 0 or capital <= 0:
            return {"error": "Invalid inputs", "position_size": 0}
        
        # Risk amount in USD
        risk_amount = capital * (risk_pct / 100.0)
        
        # SL distance based on ATR
        sl_distance = atr * self.ATR_SL_MULTIPLIER
        sl_price = entry_price - sl_distance
        
        # Position size = risk_amount / sl_distance
        position_size = risk_amount / sl_distance
        position_value = position_size * entry_price
        
        # Cap position size to 20% of capital
        max_position_value = capital * 0.20
        if position_value > max_position_value:
            position_size = max_position_value / entry_price
            position_value = max_position_value
        
        return {
            "position_size": position_size,
            "position_value_usd": position_value,
            "sl_price": sl_price,
            "sl_pct": -(sl_distance / entry_price) * 100,
            "risk_amount": risk_amount,
            "risk_pct": risk_pct,
        }
