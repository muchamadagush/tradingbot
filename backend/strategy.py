# File: backend/strategy.py
import pandas as pd
import pandas_ta as ta
from typing import Dict, Tuple, Optional
from collections import defaultdict

# ==========================================
# SIGNAL QUALITY TRACKER (P4)
# ==========================================

class SignalQualityTracker:
    """Track signal performance for quality filtering."""
    
    def __init__(self, min_trades: int = 10, min_win_rate: float = 0.40):
        self.min_trades = min_trades
        self.min_win_rate = min_win_rate
        self.signals: Dict[str, list] = defaultdict(list)  # strategy -> [(signal, result), ...]
    
    def record(self, strategy: str, signal: str, result: float):
        """Record a signal outcome (result > 0 = win)."""
        self.signals[strategy].append((signal, result))
        # Keep last 100 signals per strategy
        if len(self.signals[strategy]) > 100:
            self.signals[strategy] = self.signals[strategy][-100:]
    
    def get_win_rate(self, strategy: str) -> Tuple[float, int]:
        """Get win rate and sample size for a strategy."""
        history = self.signals.get(strategy, [])
        if not history:
            return 0.5, 0  # Default 50% if no history
        
        wins = sum(1 for _, result in history if result > 0)
        total = len(history)
        return wins / total if total > 0 else 0.5, total
    
    def is_signal_quality_ok(self, strategy: str) -> bool:
        """Check if strategy has acceptable signal quality."""
        win_rate, sample_size = self.get_win_rate(strategy)
        
        # If not enough data, allow trading
        if sample_size < self.min_trades:
            return True
        
        return win_rate >= self.min_win_rate
    
    def get_all_stats(self) -> Dict:
        """Get stats for all strategies."""
        stats = {}
        for strategy in self.signals:
            win_rate, sample_size = self.get_win_rate(strategy)
            stats[strategy] = {
                "win_rate": round(win_rate * 100, 1),
                "sample_size": sample_size,
                "is_quality_ok": self.is_signal_quality_ok(strategy),
            }
        return stats


# Global signal tracker
signal_tracker = SignalQualityTracker()


# ==========================================
# 1. RUMUS & INDIKATOR
# ==========================================

def _ema(series, length):
    return ta.ema(series, length=length)

def populate_indicators(df):
    """
    Menghitung indikator dengan Dynamic Mapping (Anti-Error).
    """
    df = df.copy()
    
    # Safety: Pastikan data numerik
    for col in ['open', 'high', 'low', 'close', 'volume']:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')

    try:
        # Hitung indikator
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.adx(length=14, append=True)
        df.ta.atr(length=14, append=True)  # P4: ATR for volatility
    except Exception as e:
        print(f"⚠️ Error calculating indicators: {e}")
        return df

    # Dynamic Column Mapping
    cols = df.columns.tolist()
    
    rsi_col = next((c for c in cols if c.startswith('RSI_')), None)
    if rsi_col: df['RSI'] = df[rsi_col]

    macd_col = next((c for c in cols if c.startswith('MACD_') and 'h' not in c and 's' not in c), None)
    sig_col = next((c for c in cols if c.startswith('MACDs_')), None)
    if macd_col: df['MACD'] = df[macd_col]
    if sig_col: df['Signal_Line'] = df[sig_col]

    upper_col = next((c for c in cols if c.startswith('BBU_')), None)
    lower_col = next((c for c in cols if c.startswith('BBL_')), None)
    if upper_col: df['Upper_BB'] = df[upper_col]
    if lower_col: df['Lower_BB'] = df[lower_col]

    adx_col = next((c for c in cols if c.startswith('ADX_')), None)
    if adx_col: df['ADX'] = df[adx_col]
    
    # +DI and -DI for trend direction
    dmp_col = next((c for c in cols if c.startswith('DMP_')), None)
    dmn_col = next((c for c in cols if c.startswith('DMN_')), None)
    if dmp_col: df['PLUS_DI'] = df[dmp_col]
    if dmn_col: df['MINUS_DI'] = df[dmn_col]
    
    atr_col = next((c for c in cols if c.startswith('ATR')), None)
    if atr_col: df['ATR'] = df[atr_col]
        
    return df

# ==========================================
# 2. LOGIKA INTI (DECISION MAKER)
# ==========================================

def decide_strategy(df):
    """
    META STRATEGY: Harmonisasi antara Breakout, Trend, dan Sideways.
    """
    last = df.iloc[-1]
    
    required_cols = ['ADX', 'Upper_BB', 'Lower_BB', 'RSI', 'close']
    if not all(col in df.columns for col in required_cols):
         return {"action": "HOLD", "reason": "Incomplete Data", "strategy": "WAITING", "adx": 0, "bb_width": 0}

    if pd.isna(last.get('ADX')):
        return {"action": "HOLD", "reason": "NaN ADX", "strategy": "WAITING", "adx": 0, "bb_width": 0}

    # Hitung Metrics
    adx_value = last['ADX']
    close_price = last['close']
    bb_width = (last['Upper_BB'] - last['Lower_BB']) / close_price if close_price != 0 else 0

    # --- SUB-STRATEGIES ---
    
    def strategy_trend():
        if len(df) < 5: return "HOLD", "Wait data"
        fast = _ema(df['close'], 9)
        slow = _ema(df['close'], 21)
        
        # BUY: Uptrend
        if fast.iloc[-1] > slow.iloc[-1]:
            # Filter: Jangan beli di pucuk (RSI > 75)
            if last['RSI'] < 75: return "BUY", "Uptrend & Healthy RSI"
            return "HOLD", "Uptrend but Overbought"
            
        # SELL: Death Cross (Trend Berakhir)
        if fast.iloc[-1] < slow.iloc[-1]:
            return "SELL", "Downtrend Confirmed"
            
        return "HOLD", "No Signal"

    def strategy_sideways():
        # Mean Reversion dengan RSI yang lebih ketat
        rsi = last['RSI']
        
        # RSI Divergence check: harga turun tapi RSI naik = bullish divergence
        has_bullish_divergence = False
        if len(df) >= 5:
            price_falling = df['close'].iloc[-1] < df['close'].iloc[-3]
            rsi_rising = df['RSI'].iloc[-1] > df['RSI'].iloc[-3]
            has_bullish_divergence = price_falling and rsi_rising
        
        # BUY: True oversold (RSI < 30) atau "cheap zone" (RSI < 35) dengan divergence
        if rsi < 30:
            return "BUY", f"RSI Oversold ({rsi:.1f})"
        if rsi < 35 and has_bullish_divergence:
            return "BUY", f"RSI Cheap + Bullish Divergence ({rsi:.1f})"
        
        # SELL: Overbought Extreem Saja
        # PERUBAHAN PENTING: Dulu 55, sekarang 72.
        # Ini mencegah bot menjual terlalu cepat saat Breakout baru terjadi.
        if rsi > 72: return "SELL", f"RSI Peak ({rsi:.1f})"
        
        return "HOLD", "RSI Neutral"

    def strategy_breakout():
        # Breakout
        # Filter RSI > 50 memastikan breakout didukung momentum beli
        if last['close'] > last['Upper_BB'] and last['RSI'] > 50: 
            return "BUY", "Valid Breakout Up"
        
        if last['close'] < last['Lower_BB']: 
            return "SELL", "Breakdown Down"
            
        return "HOLD", "Inside Squeeze"

    # --- LOGIC SWITCH (TUNING HARMONIS) ---
    selected = "UNKNOWN"
    action = "HOLD"
    reason = "Wait"
    
    # Get +DI/-DI for trend direction confirmation
    plus_di = last.get('PLUS_DI', 0)
    minus_di = last.get('MINUS_DI', 0)
    trend_direction = "UP" if plus_di > minus_di else "DOWN" if minus_di > plus_di else "NEUTRAL"

    # 1. Squeeze: Masih ketat (8%), mencari ledakan
    if bb_width < 0.08: 
        selected = "BREAKOUT"
        action, reason = strategy_breakout()
        
    # 2. Strong Trend: ADX > 35 = strong trending market
    elif adx_value > 35:
        selected = "STRONG_TREND"
        action, reason = strategy_trend()
        # Only follow trend direction
        if action == "BUY" and trend_direction == "DOWN":
            action = "HOLD"
            reason += " (Blocked: -DI > +DI)"
        elif action == "SELL" and trend_direction == "UP":
            action = "HOLD"
            reason += " (Blocked: +DI > -DI)"
        
    # 3. Moderate Trend: ADX 25-35 with DI confirmation
    elif adx_value > 25:
        selected = "TREND_FOLLOWING"
        action, reason = strategy_trend()
        # Require DI confirmation for moderate trends
        if action == "BUY" and trend_direction != "UP":
            action = "HOLD"
            reason += " (No +DI confirmation)"
        
    # 4. Sideways: ADX <= 25, mode default (mean reversion)
    else: 
        selected = "MEAN_REVERSION"
        action, reason = strategy_sideways()
    
    # P4: Get ATR for volatility-adjusted sizing
    atr_value = last.get('ATR', 0)
    atr_pct = (atr_value / close_price * 100) if close_price > 0 and atr_value else 0

    return {
        "selected_strategy": selected,
        "action": action,
        "reason": reason,
        "adx": adx_value,
        "bb_width": bb_width,
        "atr": atr_value,
        "atr_pct": atr_pct,
    }


# ==========================================
# P4: VOLATILITY-ADJUSTED POSITION SIZING
# ==========================================

def calculate_atr_position_size(
    base_risk_pct: float, 
    atr_pct: float, 
    portfolio_value: float,
    entry_price: float,
    target_atr_multiplier: float = 1.5
) -> Dict:
    """
    Calculate position size based on ATR volatility.
    
    Higher volatility = smaller position size
    Lower volatility = larger position size (up to max)
    
    Args:
        base_risk_pct: Base risk per trade (e.g., 2%)
        atr_pct: Current ATR as percentage of price
        portfolio_value: Total portfolio value
        entry_price: Entry price per unit
        target_atr_multiplier: Stop loss distance as ATR multiple
    
    Returns:
        Position sizing dict with size and stop loss
    """
    # Normalize ATR: if ATR is 2%, that's "normal" volatility
    normal_atr = 2.0
    volatility_factor = normal_atr / max(atr_pct, 0.5)  # Cap to prevent extreme values
    volatility_factor = max(0.5, min(2.0, volatility_factor))  # Clamp between 0.5x and 2x
    
    # Adjust risk based on volatility
    adjusted_risk_pct = base_risk_pct * volatility_factor
    risk_amount = portfolio_value * (adjusted_risk_pct / 100)
    
    # Calculate stop loss distance
    stop_distance_pct = atr_pct * target_atr_multiplier
    stop_price = entry_price * (1 - stop_distance_pct / 100)
    
    # Calculate position size
    risk_per_unit = entry_price - stop_price
    position_size = risk_amount / risk_per_unit if risk_per_unit > 0 else 0
    position_value = position_size * entry_price
    
    return {
        "position_size": round(position_size, 8),
        "position_value": round(position_value, 2),
        "stop_price": round(stop_price, 8),
        "stop_distance_pct": round(stop_distance_pct, 2),
        "volatility_factor": round(volatility_factor, 2),
        "adjusted_risk_pct": round(adjusted_risk_pct, 2),
        "risk_amount": round(risk_amount, 2),
    }


# ==========================================
# P4: MULTI-TIMEFRAME CONFIRMATION
# ==========================================

async def get_higher_tf_trend(exchange, symbol: str, timeframe: str = "15m") -> str:
    """
    Get trend direction from higher timeframe for confirmation.
    
    Returns: "UP", "DOWN", or "NEUTRAL"
    """
    try:
        bars = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=50)
        if not bars or len(bars) < 30:
            return "NEUTRAL"
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df['close'] = pd.to_numeric(df['close'], errors='coerce')
        
        # Calculate EMAs
        ema_fast = ta.ema(df['close'], length=9)
        ema_slow = ta.ema(df['close'], length=21)
        
        if ema_fast is None or ema_slow is None:
            return "NEUTRAL"
        
        if ema_fast.iloc[-1] > ema_slow.iloc[-1]:
            return "UP"
        elif ema_fast.iloc[-1] < ema_slow.iloc[-1]:
            return "DOWN"
        else:
            return "NEUTRAL"
            
    except Exception as e:
        print(f"⚠️ Higher TF check failed: {e}")
        return "NEUTRAL"


# ==========================================
# 3. INTERFACE LIVE TRADING (ENHANCED)
# ==========================================

async def analyze_market(exchange, symbol, use_mtf_confirm: bool = True):
    """
    Analyze market with optional multi-timeframe confirmation.
    """
    try:
        if not exchange.has['fetchOHLCV']:
            return "ERROR", 0, {}
        
        bars = await exchange.fetch_ohlcv(symbol, timeframe='1m', limit=100)
        if not bars:
            return "ERROR", 0, {}
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = populate_indicators(df)
        
        if df.empty:
            return "ERROR", 0, {}
        
        current_price = df['close'].iloc[-1]
        decision = decide_strategy(df)
        final_action = decision['action']
        strategy_name = decision['selected_strategy']
        
        # P4: Check signal quality
        if final_action == "BUY" and not signal_tracker.is_signal_quality_ok(strategy_name):
            final_action = "HOLD"
            decision['reason'] += " (Low quality signal filtered)"
        
        # P4: Multi-timeframe confirmation for BUY signals
        higher_tf_trend = "NEUTRAL"
        if use_mtf_confirm and final_action == "BUY":
            higher_tf_trend = await get_higher_tf_trend(exchange, symbol, "15m")
            
            # Only allow BUY if higher TF is UP or NEUTRAL
            if higher_tf_trend == "DOWN":
                final_action = "HOLD"
                decision['reason'] += " (Blocked by 15m downtrend)"

        indicators = {
            "rsi": df['RSI'].iloc[-1] if 'RSI' in df.columns else 0,
            "adx": decision['adx'],
            "bb_width": decision['bb_width'],
            "atr": decision.get('atr', 0),
            "atr_pct": decision.get('atr_pct', 0),
            "strategy": strategy_name,
            "reason": decision['reason'],
            "higher_tf_trend": higher_tf_trend,
            "signal_quality": signal_tracker.get_win_rate(strategy_name),
        }
        
        if final_action != "HOLD":
            print(f"📊 {symbol} | {strategy_name} | {decision['reason']} | HTF:{higher_tf_trend} -> {final_action}")
        
        return final_action, current_price, indicators

    except Exception as e:
        print(f"Error Strategy {symbol}: {e}")
        return "ERROR", 0, {}


# ==========================================
# UTILITY: Record trade outcome for signal quality
# ==========================================

def record_signal_outcome(strategy: str, signal: str, pnl: float):
    """Record trade outcome to track signal quality."""
    signal_tracker.record(strategy, signal, pnl)


def get_signal_quality_stats() -> Dict:
    """Get all signal quality statistics."""
    return signal_tracker.get_all_stats()