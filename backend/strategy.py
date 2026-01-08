# File: backend/strategy.py
import pandas as pd
import numpy as np

# ==========================================
# BAGIAN 1: RUMUS MATEMATIKA (ENGINEERING)
# ==========================================

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).fillna(0)
    loss = (-delta.where(delta < 0, 0)).fillna(0)
    avg_gain = gain.ewm(com=period-1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period-1, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    # 1. EMA Cepat & Lambat
    exp1 = series.ewm(span=fast, adjust=False).mean()
    exp2 = series.ewm(span=slow, adjust=False).mean()
    # 2. MACD Line
    macd_line = exp1 - exp2
    # 3. Signal Line
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    # 4. Histogram
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram

def calculate_bollinger_bands(series, period=20, std_dev=2):
    sma = series.rolling(window=period).mean()
    std = series.rolling(window=period).std()
    upper_band = sma + (std * std_dev)
    lower_band = sma - (std * std_dev)
    return upper_band, lower_band

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
        
        # 2. Hitung Semua Indikator (Matematika pandas tetap synchronous, ini sangat cepat jadi aman)
        # Pastikan fungsi calculate_rsi, dll sudah ada di file ini (dari kode sebelumnya)
        df['RSI'] = calculate_rsi(df['close']) 
        df['MACD'], df['Signal_Line'], _ = calculate_macd(df['close'])
        df['Upper_BB'], df['Lower_BB'] = calculate_bollinger_bands(df['close'])
        
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

        # 5. Keputusan Final
        final_action = "HOLD"
        if buy_score >= 2: final_action = "BUY"
        elif sell_score >= 2: final_action = "SELL"
        elif df['RSI'].iloc[-1] > 70: final_action = "SELL"

        indicators = {
            "rsi": df['RSI'].iloc[-1],
            "votes_buy": buy_score,
            "votes_sell": sell_score
        }
        
        # Print Debugging
        print(f"📊 {symbol} | RSI:{vote_rsi} MACD:{vote_macd} BB:{vote_bb} -> {final_action}")
        
        return final_action, current_price, indicators

    except Exception as e:
        print(f"Error Strategy {symbol}: {e}")
        return "ERROR", 0, {}