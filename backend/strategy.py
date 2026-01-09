# File: backend/strategy.py
import pandas as pd
import pandas_ta as ta

# ==========================================
# BAGIAN 1: RUMUS MATEMATIKA (ENGINEERING)
# ==========================================

def _ema(series, length):
    return ta.ema(series, length=length)

# ==========================================
# BAGIAN 2: PARA JURI (STRATEGI)
# ==========================================

def check_rsi_strategy(df):
    """Juri 1: RSI"""
    last_rsi = df['RSI'].iloc[-1]
    if last_rsi < 30: return "BUY"
    elif last_rsi > 70: return "SELL"
    return "NEUTRAL"

def check_macd_strategy(df):
    """Juri 2: MACD"""
    # Cek crossover: MACD Line memotong Signal Line ke atas (Golden Cross)
    curr_macd = df['MACD'].iloc[-1]
    curr_sig = df['Signal_Line'].iloc[-1]
    prev_macd = df['MACD'].iloc[-2]
    prev_sig = df['Signal_Line'].iloc[-2]

    # Cross UP (Beli)
    if prev_macd < prev_sig and curr_macd > curr_sig:
        return "BUY"
    # Cross DOWN (Jual)
    elif prev_macd > prev_sig and curr_macd < curr_sig:
        return "SELL"
    return "NEUTRAL"

def check_bb_strategy(df):
    """Juri 3: Bollinger Bands"""
    price = df['close'].iloc[-1]
    lower = df['Lower_BB'].iloc[-1]
    upper = df['Upper_BB'].iloc[-1]

    # Harga menyentuh/tembus bawah (Diskon)
    if price <= lower: 
        return "BUY"
    # Harga menyentuh/tembus atas (Mahal)
    elif price >= upper: 
        return "SELL"
    return "NEUTRAL"

# ==========================================
# BAGIAN 3B: META STRATEGY / BOT MANAGER
# ==========================================

def decide_strategy(df):
    """Select strategy based on market regime using ADX and BB width."""
    adx_value = df['ADX'].iloc[-1] if 'ADX' in df else 0

    middle = df['close'].rolling(window=20).mean()
    bb_width = ((df['Upper_BB'] - df['Lower_BB']) / middle).iloc[-1] if 'Upper_BB' in df and 'Lower_BB' in df else 1

    # Strategy 1: Trend following (EMA crossover) when ADX strong
    def strategy_ema(df):
        fast = _ema(df['close'], 9)
        slow = _ema(df['close'], 21)
        if fast.iloc[-2] < slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]:
            return "BUY", "EMA golden cross"
        if fast.iloc[-2] > slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]:
            return "SELL", "EMA death cross"
        return "HOLD", "EMA flat"

    # Strategy 2: Mean reversion when sideways
    def strategy_rsi(df):
        rsi = df['RSI'].iloc[-1]
        if rsi < 30:
            return "BUY", "RSI oversold"
        if rsi > 70:
            return "SELL", "RSI overbought"
        return "HOLD", "RSI neutral"

    # Strategy 3: Breakout during squeeze
    def strategy_breakout(df):
        price = df['close'].iloc[-1]
        upper = df['Upper_BB'].iloc[-1]
        lower = df['Lower_BB'].iloc[-1]
        if price > upper:
            return "BUY", "Breakout above upper BB"
        if price < lower:
            return "SELL", "Breakdown below lower BB"
        return "HOLD", "Waiting for breakout"

    selected = "MEAN_REVERSION"
    action = "HOLD"
    reason = "Default"

    # Tight squeeze first priority
    if bb_width < 0.05:
        selected = "BREAKOUT"
        action, reason = strategy_breakout(df)
    elif adx_value > 25:
        selected = "TREND_FOLLOWING"
        action, reason = strategy_ema(df)
    else:
        selected = "MEAN_REVERSION"
        action, reason = strategy_rsi(df)

    return {
        "selected_strategy": selected,
        "action": action,
        "reason": reason,
        "adx": adx_value,
        "bb_width": bb_width
    }

# ==========================================
# BAGIAN 3: MANAGER (PENGAMBIL KEPUTUSAN)
# ==========================================

async def analyze_market(exchange, symbol): # <-- Tambah 'async'
    try:
        # 1. Ambil Data Candle (Pakai await karena ini request internet)
        # ccxt async butuh 'await' di depannya
        if exchange.has['fetchOHLCV']:
            bars = await exchange.fetch_ohlcv(symbol, timeframe='1m', limit=100) # <-- Tambah 'await'
        else:
            return "ERROR", 0, {}

        if not bars: return "ERROR", 0, {}
        
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])

        # 2. Hitung indikator menggunakan pandas_ta
        df.ta.rsi(length=14, append=True)
        df.ta.macd(fast=12, slow=26, signal=9, append=True)
        df.ta.bbands(length=20, std=2, append=True)
        df.ta.adx(length=14, append=True)

        # 2b. Normalisasi nama kolom ke yang dipakai bot
        if 'RSI_14' in df:
            df['RSI'] = df['RSI_14']
        if 'MACD_12_26_9' in df:
            df['MACD'] = df['MACD_12_26_9']
        if 'MACDs_12_26_9' in df:
            df['Signal_Line'] = df['MACDs_12_26_9']
        if 'BBU_20_2.0' in df:
            df['Upper_BB'] = df['BBU_20_2.0']
        if 'BBL_20_2.0' in df:
            df['Lower_BB'] = df['BBL_20_2.0']
        if 'ADX_14' in df:
            df['ADX'] = df['ADX_14']
        
        current_price = df['close'].iloc[-1]

        # 3. Minta Pendapat Para Juri
        vote_rsi = check_rsi_strategy(df)
        vote_macd = check_macd_strategy(df)
        vote_bb = check_bb_strategy(df)

        # 4. Hitung Skor
        buy_score = 0
        sell_score = 0
        if vote_rsi == "BUY": buy_score += 1
        if vote_macd == "BUY": buy_score += 1
        if vote_bb == "BUY": buy_score += 1
        if vote_rsi == "SELL": sell_score += 1
        if vote_macd == "SELL": sell_score += 1
        if vote_bb == "SELL": sell_score += 1

        # 5. Meta Strategy decides which weapon to use
        manager = decide_strategy(df)

        final_action = manager['action'] if manager['action'] != "HOLD" else "HOLD"
        # Fallback to vote-based if manager is neutral
        if final_action == "HOLD":
            if buy_score >= 2: final_action = "BUY"
            elif sell_score >= 2: final_action = "SELL"
            elif df['RSI'].iloc[-1] > 70: final_action = "SELL"

        indicators = {
            "rsi": df['RSI'].iloc[-1],
            "votes_buy": buy_score,
            "votes_sell": sell_score,
            "adx": manager['adx'],
            "bb_width": manager['bb_width'],
            "strategy": manager['selected_strategy'],
            "strategy_reason": manager['reason']
        }
        
        # Print Debugging
        print(f"📊 {symbol} | RSI:{vote_rsi} MACD:{vote_macd} BB:{vote_bb} -> {final_action}")
        
        return final_action, current_price, indicators

    except Exception as e:
        print(f"Error Strategy {symbol}: {e}")
        return "ERROR", 0, {}