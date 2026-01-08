# File: backend/main.py
import os
import ccxt.async_support as ccxt
import asyncio
import database
import strategy 
import solana_tracker
import sys_logger

# --- IMPORT MODUL PENTING ---
from jupiter_handler import jupiter_bot
from solana_auto import solana_auto  # <--- WAJIB ADA AGAR TIDAK ERROR

from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()
app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- SETUP EXCHANGE (TOKOCRYPTO) ---
exchange = ccxt.tokocrypto({
    'apiKey': os.getenv('TOKO_API_KEY'),
    'secret': os.getenv('TOKO_SECRET_KEY'),
    'enableRateLimit': True, 
})

IS_BOT_RUNNING = False
CURRENT_SCAN_TARGET = "Idle"

class TradeSignal(BaseModel):
    symbol: str
    action: str

class SwapRequest(BaseModel):
    amount: float
    input_token: str = "SOL"
    output_token: str = "USDC"

# --- DATABASE HELPERS ---
def get_any_active_trade():
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades WHERE status = 'OPEN' LIMIT 1")
    trade = cursor.fetchone()
    conn.close()
    return trade

def save_buy_trade(symbol, price, amount, usdt):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO trades (symbol, side, buy_price, amount, total_usdt, status) VALUES (?, 'BUY', ?, ?, ?, 'OPEN')", (symbol, price, amount, usdt))
    conn.commit()
    conn.close()

def save_sell_trade(trade_id, sell_price, profit):
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE trades SET status = 'CLOSED', sell_price = ?, profit_usdt = ?, closed_at = CURRENT_TIMESTAMP WHERE id = ?", (sell_price, profit, trade_id))
    conn.commit()
    conn.close()

# --- MARKET SCANNER ---
async def get_top_liquid_coins(limit=10):
    try:
        tickers = await exchange.fetch_tickers()
        valid_pairs = []
        blacklist_base = ['USDC', 'BUSD', 'TUSD', 'USDP', 'FDUSD', 'DAI', 'EUR', 'USDT'] 

        for symbol, data in tickers.items():
            if "USDT" not in symbol: continue
            
            clean_symbol = symbol
            base_currency = ""
            if '/' in symbol:
                parts = symbol.split('/')
                if parts[1] != 'USDT': continue
                base_currency = parts[0]
                clean_symbol = symbol
            else:
                if symbol.endswith('USDT'):
                    base_currency = symbol[:-4]
                    clean_symbol = f"{base_currency}/USDT"
                elif symbol.endswith('_USDT'):
                    base_currency = symbol[:-5]
                    clean_symbol = f"{base_currency}/USDT"
                else:
                    continue

            if base_currency in blacklist_base: continue
            
            vol = data.get('quoteVolume')
            if vol is None: vol = 0
            valid_pairs.append({'symbol': clean_symbol, 'volume': float(vol)})

        sorted_pairs = sorted(valid_pairs, key=lambda x: x['volume'], reverse=True)
        top_symbols = [p['symbol'] for p in sorted_pairs[:limit]]
        
        if not top_symbols: return ["BTC/USDT", "ETH/USDT", "SOL/USDT"]
        return top_symbols

    except Exception as e:
        print(f"⚠️ [ERROR SCAN]: {e}")
        return ["BTC/USDT", "ETH/USDT", "SOL/USDT"]

# --- JANTUNG BOT HUNTER ---
async def auto_trading_loop():
    global CURRENT_SCAN_TARGET
    print("🚀 Bot Hunter Mode: ON (Brute Force)")
    try: await exchange.load_markets()
    except: pass

    TP_PERCENT = 0.015
    SL_PERCENT = 0.03
    
    while IS_BOT_RUNNING:
        active_trade = get_any_active_trade()
        
        if active_trade:
            symbol = active_trade['symbol']
            CURRENT_SCAN_TARGET = f"Managing {symbol}"
            try:
                ticker = await exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                signal, _, _ = await strategy.analyze_market(exchange, symbol)
                
                buy_price = active_trade['buy_price']
                pnl = (current_price - buy_price) / buy_price
                
                should_sell = False
                reason = ""
                if pnl > TP_PERCENT: should_sell, reason = True, "✅ TAKE PROFIT"
                elif pnl < -SL_PERCENT: should_sell, reason = True, "🛡️ STOP LOSS"
                elif signal == "SELL": should_sell, reason = True, "📉 STRATEGY SELL"

                if should_sell:
                     print(f"🔴 SELL {symbol} | {reason}")
                     profit = (current_price - buy_price) * active_trade['amount']
                     save_sell_trade(active_trade['id'], current_price, profit)
                else:
                    print(f"👀 {symbol} PnL: {pnl*100:.2f}%")
            except Exception as e:
                 print(f"Error Managing: {e}")
            await asyncio.sleep(2)

        else:
            top_coins = await get_top_liquid_coins(limit=10)
            for symbol in top_coins:
                if not IS_BOT_RUNNING: break
                CURRENT_SCAN_TARGET = f"Analyzing {symbol}" 
                try:
                    signal, price, indicators = await strategy.analyze_market(exchange, symbol)
                    if signal == "BUY":
                        print(f"🟢 FOUND GEM: {symbol}!")
                        save_buy_trade(symbol, price, 100/price, 100)
                        break 
                    await asyncio.sleep(2.0)
                except Exception as e:
                    print(f"⚠️ Skip {symbol}: {e}")
            
            CURRENT_SCAN_TARGET = "Idle"
            await asyncio.sleep(3)

    try: await exchange.close()
    except: pass
    print("🛑 Bot Berhenti.")

# ==========================================
# ENDPOINTS API
# ==========================================

@app.get("/")
def home(): return {"status": "Ready"}

# --- BOT HUNTER CONTROL ---
@app.post("/api/bot/toggle")
async def toggle_bot(background_tasks: BackgroundTasks):
    global IS_BOT_RUNNING
    if IS_BOT_RUNNING:
        IS_BOT_RUNNING = False
        return {"status": "stopped", "message": "Bot dimatikan."}
    else:
        IS_BOT_RUNNING = True
        background_tasks.add_task(auto_trading_loop)
        return {"status": "running", "message": "Bot dijalankan!"}

@app.get("/api/bot/status")
def get_bot_status():
    return {"is_running": IS_BOT_RUNNING, "current_activity": CURRENT_SCAN_TARGET}

@app.get("/api/trade/history")
def get_history():
    conn = database.get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM trades ORDER BY id DESC LIMIT 20")
    trades = cursor.fetchall()
    conn.close()
    return trades

@app.get("/api/toko/price/{symbol}")
async def get_price(symbol: str):
    try:
        if "USDT" in symbol and "/" not in symbol:
            base = symbol.replace("USDT", "")
            formatted = f"{base}/USDT"
        else:
            formatted = symbol.replace("USDT", "/USDT")
        ticker = await exchange.fetch_ticker(formatted)
        return {"current_price": ticker['last'], "high_24h": ticker['high'], "low_24h": ticker['low']}
    except:
        return {"current_price": 0, "high_24h": 0, "low_24h": 0}

# --- SOLANA & JUPITER ENDPOINTS ---

@app.get("/api/solana/balance")
async def get_solana_balance():
    """Mengambil semua saldo token di dompet (SOL, USDC, BONK, dll)"""
    return await jupiter_bot.get_token_balances()

@app.get("/api/solana/quote")
async def get_jupiter_quote(amount: float = 0.01, to_token: str = "USDC"):
    """Cek harga SOL ke Token tertentu"""
    result = await jupiter_bot.get_quote(
        input_token="SOL", 
        output_token=to_token, 
        amount_sol=amount
    )
    return result

@app.post("/api/solana/swap")
async def execute_solana_swap(request: SwapRequest):
    """Eksekusi Swap Manual"""
    quote = await jupiter_bot.get_quote(
        input_token=request.input_token,
        output_token=request.output_token,
        amount_sol=request.amount
    )
    
    if "error" in quote:
        return {"status": "error", "message": quote["error"]}
        
    result = await jupiter_bot.execute_swap(quote['raw_data'])
    
    if "status" in result and result["status"] == "success":
        solana_tracker.save_trade(
            txid=result.get("txid", "UNKNOWN"),
            input_token=request.input_token,
            output_token=request.output_token,
            input_amount=request.amount,
            output_estimate=quote.get("output_estimate", 0)
        )
    
    return result

@app.get("/api/solana/history")
async def get_solana_history():
    """Mengambil riwayat transaksi Solana"""
    return solana_tracker.load_history()

# --- SOLANA AUTO & GOD MODE ENDPOINTS ---

@app.post("/api/solana/auto/toggle")
async def toggle_solana_auto(request: dict):
    """Saklar untuk Menyalakan/Mematikan Auto Bot"""
    mode = request.get("mode", "MANUAL_TARGET") 
    token = request.get("token", "USDC")
    
    if solana_auto.is_running:
        solana_auto.stop()
        return {"status": "stopped", "message": "Auto Stopped"}
    else:
        asyncio.create_task(solana_auto.start(mode=mode, token_symbol=token))
        return {"status": "running", "message": f"Auto Started in {mode}"}

@app.get("/api/solana/auto/status")
async def get_solana_auto_status():
    """Status Real-time Auto Bot"""
    return {
        "is_running": solana_auto.is_running,
        "target": solana_auto.target_token,
        "mode": solana_auto.mode,
        "position": solana_auto.active_position
    }

# --- SYSTEM LOGS ---
@app.get("/api/system/logs")
def get_system_logs():
    """Mengambil 50 log terakhir dari scanner & bot"""
    return sys_logger.get_logs()