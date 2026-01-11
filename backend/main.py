# File: backend/main.py
import os
import ccxt.async_support as ccxt
import asyncio
import database
import strategy 
import solana_tracker
import sys_logger

# --- NEW IMPORTS untuk Safety Features ---
import backtesting
import paper_trading
import fee_calculator
from risk_manager import RiskManager, RiskLimits

# --- IMPORT MODUL PENTING ---
from jupiter_handler import jupiter_bot
from solana_auto import solana_auto  # <--- WAJIB ADA AGAR TIDAK ERROR
import analytics  # <--- Import Analytics Module

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

# --- BOT MODE CONFIGURATION ---
BOT_MODE = os.getenv('BOT_MODE', 'PAPER').upper()  # LIVE, PAPER, or BACKTEST
PAPER_INITIAL_BALANCE = float(os.getenv('PAPER_INITIAL_BALANCE', '1000.0'))

# Initialize Risk Manager
risk_limits = RiskLimits(
    max_position_size_pct=float(os.getenv('MAX_POSITION_SIZE_PCT', '20.0')),
    max_portfolio_drawdown_pct=float(os.getenv('MAX_PORTFOLIO_DRAWDOWN_PCT', '15.0')),
    max_daily_loss_pct=float(os.getenv('MAX_DAILY_LOSS_PCT', '5.0')),
    max_open_positions=int(os.getenv('MAX_OPEN_POSITIONS', '5')),
    risk_per_trade_pct=float(os.getenv('RISK_PER_TRADE_PCT', '2.0'))
)
risk_manager = RiskManager(PAPER_INITIAL_BALANCE, risk_limits)

# Initialize Fee Calculator
fee_calc = fee_calculator.get_calculator(
    exchange_id='tokocrypto',
    slippage_pct=float(os.getenv('SLIPPAGE_PCT', '0.0005'))
)

print(f"{'='*60}")
print(f"🤖 TRADING BOT STARTED")
print(f"{'='*60}")
print(f"🎯 Mode: {BOT_MODE}")
if BOT_MODE == 'PAPER':
    print(f"💵 Paper Balance: ${paper_trading.paper_account.balance:.2f}")
elif BOT_MODE == 'LIVE':
    print(f"⚠️  LIVE TRADING MODE - REAL MONEY AT RISK!")
print(f"🛡️ Risk Management: ENABLED")
print(f"   - Max Position: {risk_limits.max_position_size_pct}%")
print(f"   - Max Drawdown: {risk_limits.max_portfolio_drawdown_pct}%")
print(f"   - Risk/Trade: {risk_limits.risk_per_trade_pct}%")
print(f"{'='*60}\n")

# Add logs to system logger
sys_logger.add_log(f"✅ TRADING BOT STARTED - Mode: {BOT_MODE}")
sys_logger.add_log(f"💵 Initial Balance: ${PAPER_INITIAL_BALANCE:.2f}")
sys_logger.add_log(f"🛡️  Risk Management: Enabled")
sys_logger.add_log(f"🔗 API Connection: Ready")

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
    print("🚀 Bot Hunter Mode: ON (Real Execution Ready)")
    sys_logger.add_log("🚀 Bot Loop Started")
    
    # Load market agar simbol terupdate
    try: await exchange.load_markets()
    except: pass

    # --- KONFIGURASI DASAR ---
    TP_PERCENT = 0.015  # Take Profit 1.5%
    SL_PERCENT = 0.03   # Stop Loss 3.0%
    TRADE_AMOUNT_USDT = 12.0 # Modal per trade (Min $10 di Toko)
    
    while IS_BOT_RUNNING:
        # 1. MANAGEMENT POSISI (Jual jika TP/SL)
        active_trade = get_any_active_trade()
        
        if active_trade:
            symbol = active_trade['symbol']
            CURRENT_SCAN_TARGET = f"Managing {symbol}"
            try:
                ticker = await exchange.fetch_ticker(symbol)
                current_price = ticker['last']
                
                # Analisa ulang (Opsional, bisa dihapus jika murni TP/SL)
                signal, _, _ = await strategy.analyze_market(exchange, symbol)
                
                buy_price = active_trade['buy_price']
                amount = active_trade['amount']
                pnl_pct = (current_price - buy_price) / buy_price
                
                should_sell = False
                reason = ""
                
                # Logic Penjualan
                if pnl_pct > TP_PERCENT: should_sell, reason = True, f"✅ TAKE PROFIT (+{pnl_pct*100:.2f}%)"
                elif pnl_pct < -SL_PERCENT: should_sell, reason = True, f"🛡️ STOP LOSS ({pnl_pct*100:.2f}%)"
                elif signal == "SELL": should_sell, reason = True, "📉 STRATEGY SELL"

                if should_sell:
                    print(f"🔴 EXECUTING SELL {symbol} | {reason}")
                    sys_logger.add_log(f"🔴 SELL {symbol} | {reason}")
                    
                    # --- [FIX] EKSEKUSI REAL KE EXCHANGE ---
                    if BOT_MODE == 'LIVE':
                        try:
                            # Kirim Order Jual ke Tokocrypto
                            order = await exchange.create_market_sell_order(symbol, amount)
                            sys_logger.add_log(f"✅ REAL SOLD: {order['id']}")
                        except Exception as e:
                            sys_logger.add_log(f"❌ SELL FAILED: {e}")
                            # Jangan update database jika gagal jual di exchange (kecuali mau force close)
                    
                    # Simpan ke DB & Update Risk Manager
                    profit_usdt = (current_price - buy_price) * amount
                    save_sell_trade(active_trade['id'], current_price, profit_usdt)
                    risk_manager.record_trade_pnl(profit_usdt) # Penting untuk hitung kuota rugi harian

                else:
                    print(f"👀 {symbol} PnL: {pnl_pct*100:.2f}%")
            
            except Exception as e:
                 print(f"Error Managing: {e}")
            await asyncio.sleep(2)

        # 2. SCANNING POSISI BARU (Beli)
        else:
            # --- [FIX] Validasi Risk Manager Sebelum Scan ---
            if not risk_manager.can_trade_new():
                CURRENT_SCAN_TARGET = "Risk Limit Reached"
                sys_logger.add_log("🛑 Daily Loss Limit Reached / Max Drawdown Hit")
                await asyncio.sleep(60) # Istirahat 1 menit
                continue

            top_coins = await get_top_liquid_coins(limit=10)
            
            for symbol in top_coins:
                if not IS_BOT_RUNNING: break
                CURRENT_SCAN_TARGET = f"Analyzing {symbol}" 
                
                try:
                    # Analisa Teknikal
                    signal, price, indicators = await strategy.analyze_market(exchange, symbol)
                    
                    if signal == "BUY":
                        # Cek Saldo Real
                        balance = await exchange.fetch_balance()
                        usdt_balance = balance['USDT']['free']
                        
                        # Cek Izin Risk Manager
                        current_positions = 0 # Karena limit 1 trade aktif
                        risk_check = risk_manager.can_open_position(current_positions, usdt_balance, TRADE_AMOUNT_USDT)
                        
                        if risk_check['approved']:
                            print(f"🟢 FOUND GEM: {symbol} @ {price}")
                            sys_logger.add_log(f"🟢 BUY SIGNAL: {symbol}")
                            
                            amount_coin = TRADE_AMOUNT_USDT / price
                            
                            # --- [FIX] EKSEKUSI REAL KE EXCHANGE ---
                            if BOT_MODE == 'LIVE':
                                if usdt_balance >= TRADE_AMOUNT_USDT:
                                    try:
                                        # Kirim Order Beli ke Tokocrypto
                                        order = await exchange.create_market_buy_order(symbol, amount_coin)
                                        sys_logger.add_log(f"✅ REAL BOUGHT: {order['id']}")
                                        
                                        # Simpan ke DB hanya jika sukses beli
                                        save_buy_trade(symbol, price, amount_coin, TRADE_AMOUNT_USDT)
                                        break # Stop scanning, fokus manage posisi ini
                                    except Exception as e:
                                        sys_logger.add_log(f"❌ BUY FAILED: {e}")
                                else:
                                    sys_logger.add_log("⚠️ Saldo USDT Tidak Cukup")
                            
                            # MODE PAPER/TEST
                            else:
                                save_buy_trade(symbol, price, amount_coin, TRADE_AMOUNT_USDT)
                                break
                        else:
                            print(f"🛑 Skip {symbol}: Risk Rejected ({risk_check['reasons']})")
                    
                    await asyncio.sleep(1.0) # Jeda antar koin
                    
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
        sys_logger.add_log("🛑 Hunter Bot: STOPPED")
        return {"status": "stopped", "message": "Bot dimatikan."}
    else:
        IS_BOT_RUNNING = True
        sys_logger.add_log("🚀 Hunter Bot: STARTED - Scanning markets...")
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
        # Untuk manual swap, kita cari mint address dari output_token
        token_address = TOKENS.get(request.output_token, request.output_token) if request.input_token == "SOL" else TOKENS.get(request.input_token, request.input_token)
        solana_tracker.save_trade(
            txid=result.get("txid", "UNKNOWN"),
            input_token=request.input_token,
            output_token=request.output_token,
            input_amount=request.amount,
            output_estimate=quote.get("output_estimate", 0),
            token_address=token_address
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
    strategy = request.get("strategy", "TRADER")
    strategy = strategy.upper() if isinstance(strategy, str) else "TRADER"
    if strategy not in ("SNIPER", "TRADER"):
        strategy = "TRADER"
    
    if solana_auto.is_running:
        # Jika mode & strategi sama, stop bot
        if solana_auto.mode == mode and solana_auto.strategy == strategy:
            solana_auto.stop()
            return {"status": "stopped", "message": "Auto Stopped"}
        # Jika mode berbeda, restart dengan mode baru
        else:
            solana_auto.stop()
            await asyncio.sleep(0.5)  # Tunggu bot berhenti sepenuhnya
            asyncio.create_task(solana_auto.start(mode=mode, token_symbol=token, strategy=strategy))
            return {"status": "running", "message": f"Auto Restarted in {mode} ({strategy})"}
    else:
        asyncio.create_task(solana_auto.start(mode=mode, token_symbol=token, strategy=strategy))
        return {"status": "running", "message": f"Auto Started in {mode} ({strategy})"}

@app.get("/api/solana/auto/status")
async def get_solana_auto_status():
    """Get status of Solana Auto Bot"""
    return {
        "is_running": solana_auto.is_running,
        "mode": solana_auto.mode,
        "strategy": solana_auto.strategy,
        "target": solana_auto.target_token,
        # UPDATE DI SINI: Gunakan 'positions' (plural) dan ambil list active_positions
        "positions": solana_auto.active_positions, 
        "count": len(solana_auto.active_positions)
    }

# --- SYSTEM LOGS ---
@app.get("/api/system/logs")
def get_system_logs():
    """Mengambil 50 log terakhir dari scanner & bot"""
    logs = sys_logger.get_logs()
    print(f"[DEBUG] Returning {len(logs)} logs to frontend")
    return logs

# ==========================================
# 🆕 BACKTESTING ENDPOINTS
# ==========================================

@app.post("/api/backtest/run")
async def run_backtest(request: dict):
    """
    Run backtest untuk strategi Tokocrypto (Voting System + Risk Manager)
    
    Body:
        {
            "symbol": "BTC/USDT",
            "timeframe": "1h",
            "days_back": 30,
            "initial_capital": 1000,
            "take_profit_pct": 1.5,
            "stop_loss_pct": 3.0,
            "enable_risk_manager": true,
            "trade_amount_usdt": 12.0
        }
    """
    symbol = request.get('symbol', 'BTC/USDT')
    timeframe = request.get('timeframe', '1h')
    days_back = request.get('days_back', 30)
    initial_capital = request.get('initial_capital', 1000.0)
    take_profit_pct = request.get('take_profit_pct', 1.5)
    stop_loss_pct = request.get('stop_loss_pct', 3.0)
    enable_risk_manager = request.get('enable_risk_manager', True)
    trade_amount_usdt = request.get('trade_amount_usdt', 12.0)
    
    engine = backtesting.BacktestEngine(
        initial_capital=initial_capital,
        enable_risk_manager=enable_risk_manager,
        trade_amount_usdt=trade_amount_usdt
    )
    result = await engine.run_backtest(
        symbol=symbol,
        timeframe=timeframe,
        days_back=days_back,
        take_profit_pct=take_profit_pct,
        stop_loss_pct=stop_loss_pct
    )
    
    # Save to database
    if 'error' not in result:
        database.save_backtest_result(result)
    
    return result

@app.post("/api/backtest/batch")
async def run_batch_backtest(request: dict):
    """
    Run backtest untuk multiple symbols dengan strategi Tokocrypto
    
    Body:
        {
            "symbols": ["BTC/USDT", "ETH/USDT", "SOL/USDT"],
            "timeframe": "1h",
            "days_back": 30,
            "enable_risk_manager": true,
            "trade_amount_usdt": 12.0
        }
    """
    symbols = request.get('symbols', ['BTC/USDT', 'ETH/USDT'])
    timeframe = request.get('timeframe', '1h')
    days_back = request.get('days_back', 30)
    enable_risk_manager = request.get('enable_risk_manager', True)
    trade_amount_usdt = request.get('trade_amount_usdt', 12.0)
    
    results = await backtesting.batch_backtest(
        symbols, 
        timeframe, 
        days_back,
        enable_risk_manager=enable_risk_manager,
        trade_amount_usdt=trade_amount_usdt
    )
    
    # Save all to database
    for result in results:
        if 'error' not in result:
            database.save_backtest_result(result)
    
    return {"status": "completed", "results": results}

@app.get("/api/backtest/history")
def get_backtest_history(limit: int = 10):
    """Get backtest history from database"""
    history = database.get_backtest_history(limit)
    return [dict(row) for row in history]

# ==========================================
# 🆕 PAPER TRADING ENDPOINTS
# ==========================================

@app.get("/api/paper/account")
async def get_paper_account():
    """Get paper trading account summary"""
    # Get current prices
    current_prices = {}
    for symbol in paper_trading.paper_account.positions.keys():
        try:
            ticker = await exchange.fetch_ticker(symbol)
            current_prices[symbol] = ticker['last']
        except:
            pass
    
    return paper_trading.paper_account.get_account_summary(current_prices)

@app.post("/api/paper/buy")
async def paper_buy(request: dict):
    """
    Place paper trading buy order
    
    Body:
        {
            "symbol": "BTC/USDT",
            "amount_usdt": 100
        }
    """
    symbol = request.get('symbol')
    amount_usdt = request.get('amount_usdt')
    
    if not symbol or not amount_usdt:
        return {"status": "error", "message": "Missing symbol or amount_usdt"}
    
    # Get current price
    try:
        ticker = await exchange.fetch_ticker(symbol)
        current_price = ticker['last']
    except Exception as e:
        return {"status": "error", "message": f"Failed to get price: {e}"}
    
    # Check risk management
    current_positions = len(paper_trading.paper_account.positions)
    risk_check = risk_manager.can_open_position(
        current_positions=current_positions,
        current_capital=paper_trading.paper_account.balance,
        new_position_value=amount_usdt
    )
    
    if not risk_check['approved']:
        return {
            "status": "rejected",
            "message": "Risk management check failed",
            "reasons": risk_check['reasons']
        }
    
    # Execute paper buy
    result = paper_trading.paper_account.place_market_buy(symbol, amount_usdt, current_price)
    
    if result['status'] == 'success':
        risk_manager.update_peak_capital(paper_trading.paper_account.balance)
    
    return result

@app.post("/api/paper/sell")
async def paper_sell(request: dict):
    """
    Place paper trading sell order
    
    Body:
        {
            "symbol": "BTC/USDT",
            "percentage": 100
        }
    """
    symbol = request.get('symbol')
    percentage = request.get('percentage', 100)
    
    if not symbol:
        return {"status": "error", "message": "Missing symbol"}
    
    # Get current price
    try:
        ticker = await exchange.fetch_ticker(symbol)
        current_price = ticker['last']
    except Exception as e:
        return {"status": "error", "message": f"Failed to get price: {e}"}
    
    # Execute paper sell
    result = paper_trading.paper_account.place_market_sell(symbol, percentage, current_price)
    
    if result['status'] == 'success' and 'trade' in result:
        # Record trade P&L for risk tracking
        risk_manager.record_trade_pnl(result['trade']['profit'])
        risk_manager.update_peak_capital(paper_trading.paper_account.balance)
    
    return result

@app.post("/api/paper/reset")
def reset_paper_account(request: dict):
    """Reset paper trading account"""
    new_balance = request.get('balance', PAPER_INITIAL_BALANCE)
    paper_trading.paper_account.reset_account(new_balance)
    risk_manager.initial_capital = new_balance
    risk_manager.peak_capital = new_balance
    risk_manager.daily_pnl = 0
    return {"status": "success", "message": f"Account reset to ${new_balance}"}

@app.get("/api/paper/orders")
def get_paper_orders():
    """Get paper trading order history"""
    return paper_trading.paper_account.orders_history

@app.get("/api/paper/trades")
def get_paper_trades():
    """Get completed paper trades"""
    return paper_trading.paper_account.trades_history

# ==========================================
# 🆕 FEE CALCULATOR ENDPOINTS
# ==========================================

@app.post("/api/fee/calculate-buy")
def calculate_buy_fee(request: dict):
    """
    Calculate buy cost with fees
    
    Body:
        {
            "amount_usdt": 100,
            "price": 50000,
            "order_type": "market"
        }
    """
    return fee_calc.calculate_buy_cost(
        request.get('amount_usdt'),
        request.get('price'),
        request.get('order_type', 'market')
    )

@app.post("/api/fee/calculate-sell")
def calculate_sell_fee(request: dict):
    """
    Calculate sell proceeds with fees
    
    Body:
        {
            "asset_amount": 0.002,
            "price": 50000,
            "order_type": "market"
        }
    """
    return fee_calc.calculate_sell_proceeds(
        request.get('asset_amount'),
        request.get('price'),
        request.get('order_type', 'market')
    )

@app.post("/api/fee/round-trip")
def calculate_round_trip(request: dict):
    """
    Calculate round-trip cost (buy + sell)
    
    Body:
        {
            "amount_usdt": 100,
            "price": 50000
        }
    """
    return fee_calc.calculate_round_trip_cost(
        request.get('amount_usdt'),
        request.get('price')
    )

@app.post("/api/fee/profit-target")
def calculate_profit_target(request: dict):
    """
    Calculate target sell price for desired profit
    
    Body:
        {
            "buy_price": 50000,
            "amount": 0.002,
            "target_profit_pct": 5
        }
    """
    return fee_calc.calculate_profit_target(
        request.get('buy_price'),
        request.get('amount'),
        request.get('target_profit_pct')
    )

# ==========================================
# 🆕 RISK MANAGEMENT ENDPOINTS
# ==========================================

@app.post("/api/risk/position-size")
def calculate_position_size(request: dict):
    """
    Calculate optimal position size
    
    Body:
        {
            "capital": 1000,
            "entry_price": 50000,
            "stop_loss_price": 48500
        }
    """
    return risk_manager.calculate_position_size(
        request.get('capital'),
        request.get('entry_price'),
        request.get('stop_loss_price')
    )

@app.get("/api/risk/summary")
async def get_risk_summary():
    """Get risk management summary"""
    # Get current prices for paper account
    current_prices = {}
    for symbol in paper_trading.paper_account.positions.keys():
        try:
            ticker = await exchange.fetch_ticker(symbol)
            current_prices[symbol] = ticker['last']
        except:
            pass
    
    equity = paper_trading.paper_account.get_total_equity(current_prices)
    open_positions = len(paper_trading.paper_account.positions)
    
    return risk_manager.get_risk_summary(equity, open_positions)

@app.post("/api/risk/kelly")
def calculate_kelly(request: dict):
    """
    Calculate Kelly Criterion
    
    Body:
        {
            "win_rate": 55,
            "avg_win": 50,
            "avg_loss": 30
        }
    """
    return risk_manager.calculate_kelly_criterion(
        request.get('win_rate'),
        request.get('avg_win'),
        request.get('avg_loss')
    )

# ==========================================
# 🆕 MODE SWITCHING ENDPOINTS
# ==========================================

@app.get("/api/bot/mode")
def get_bot_mode():
    """Get current bot mode"""
    return {
        "mode": BOT_MODE,
        "description": {
            "LIVE": "Real money trading (DANGEROUS)",
            "PAPER": "Virtual money trading (SAFE)",
            "BACKTEST": "Historical data testing"
        }.get(BOT_MODE, "Unknown")
    }

# ==========================================
# 🆕 ANALYTICS ENDPOINTS
# ==========================================

@app.get("/api/analytics/solana")
def get_solana_analytics(
    start_date: str = None,
    end_date: str = None,
    timeframe: str = "daily"
):
    """
    Get Solana trading analytics with profit/loss calculations
    
    Query Parameters:
        - start_date: ISO format (YYYY-MM-DD) - optional
        - end_date: ISO format (YYYY-MM-DD) - optional
        - timeframe: 'daily' (default), 'weekly', 'monthly', 'yearly'
    
    Returns:
        {
            "data": [
                {
                    "date": "2024-01-01",
                    "profit_sol": 0.5,
                    "profit_usd": 100,
                    "cumulative_profit_sol": 0.5,
                    "cumulative_profit_usd": 100
                },
                ...
            ],
            "summary": {
                "total_profit_sol": 5.0,
                "total_profit_usd": 1000.0,
                "total_loss_sol": -2.0,
                "total_loss_usd": -400.0,
                "net_profit_sol": 3.0,
                "net_profit_usd": 600.0,
                "total_trades": 20,
                "winning_trades": 15,
                "losing_trades": 5,
                "win_rate": 75.0
            }
        }
    """
    # Get current SOL price (default 200, should be fetched from API)
    sol_price = 200.0
    
    result = analytics.calculate_solana_analytics(
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe,
        sol_to_usd=sol_price
    )
    
    return result


@app.get("/api/analytics/tokocrypto")
def get_tokocrypto_analytics(
    start_date: str = None,
    end_date: str = None,
    timeframe: str = "daily"
):
    """
    Get Tokocrypto trading analytics with profit/loss calculations
    
    Query Parameters:
        - start_date: ISO format (YYYY-MM-DD) - optional
        - end_date: ISO format (YYYY-MM-DD) - optional
        - timeframe: 'daily' (default), 'weekly', 'monthly', 'yearly'
    
    Returns:
        {
            "data": [
                {
                    "date": "2024-01-01",
                    "profit_usdt": 100,
                    "cumulative_profit": 100
                },
                ...
            ],
            "summary": {
                "total_profit_usdt": 500,
                "total_loss_usdt": -200,
                "net_profit_usdt": 300,
                "total_trades": 20,
                "winning_trades": 15,
                "losing_trades": 5,
                "win_rate": 75.0
            }
        }
    """
    result = analytics.calculate_tokocrypto_analytics(
        start_date=start_date,
        end_date=end_date,
        timeframe=timeframe
    )
    
    return result
