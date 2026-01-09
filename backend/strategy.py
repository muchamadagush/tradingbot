# File: backend/strategy.py
import pandas as pd
import pandas_ta as ta

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
        # Mean Reversion
        rsi = last['RSI']
        
        # BUY: Oversold
        if rsi < 45: return "BUY", f"RSI Cheap ({rsi:.1f})"
        
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

    # 1. Squeeze: Masih ketat (8%), mencari ledakan
    if bb_width < 0.08: 
        selected = "BREAKOUT"
        action, reason = strategy_breakout()
        
    # 2. Trend: Batas diturunkan ke 20 agar lebih cepat mendeteksi 'Follow Through' dari Breakout
    elif adx_value > 20: 
        selected = "TREND_FOLLOWING"
        action, reason = strategy_trend()
        
    # 3. Sideways: Mode default
    else: 
        selected = "MEAN_REVERSION"
        action, reason = strategy_sideways()

    return {
        "selected_strategy": selected,
        "action": action,
        "reason": reason,
        "adx": adx_value,
        "bb_width": bb_width
    }

# ==========================================
# 3. INTERFACE LIVE TRADING
# ==========================================

async def analyze_market(exchange, symbol):
    try:
        if exchange.has['fetchOHLCV']:
            bars = await exchange.fetch_ohlcv(symbol, timeframe='1m', limit=100)
        else: return "ERROR", 0, {}

        if not bars: return "ERROR", 0, {}
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        df = populate_indicators(df)
        
        if df.empty: return "ERROR", 0, {}
        current_price = df['close'].iloc[-1]

        decision = decide_strategy(df)
        final_action = decision['action']

        indicators = {
            "rsi": df['RSI'].iloc[-1] if 'RSI' in df.columns else 0,
            "adx": decision['adx'],
            "bb_width": decision['bb_width'],
            "strategy": decision['selected_strategy'],
            "reason": decision['reason']
        }
        
        if final_action != "HOLD":
            print(f"📊 {symbol} | {decision['selected_strategy']} | {decision['reason']} -> {final_action}")
        
        return final_action, current_price, indicators

    except Exception as e:
        print(f"Error Strategy {symbol}: {e}")
        return "ERROR", 0, {}