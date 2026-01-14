# ==========================================
# File: backend/main.py
# ==========================================

import os
import asyncio
import ccxt.async_support as ccxt
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# NumPy for type conversion (optional but recommended)
try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    np = None
    HAS_NUMPY = False

# Load environment early so DATABASE_URL is available for database imports
load_dotenv()

import strategy
import solana_tracker
import sys_logger
import analytics

import backtesting
import paper_trading
import fee_calculator
import execution  # P3: Execution utilities with retry and order book check

# Import directly from PostgreSQL database layer (NOT SQLite wrapper)
from database_pg import (
    get_db_session, Trade, TradeState, TradeLedger,
    session_scope, get_account_balance, update_account_balance
)
from risk_manager import BotRiskRegistry
from jupiter_handler import jupiter_bot
from solana_auto import solana_auto
from global_kill_switch import kill_switch
from websocket_manager import ws_manager, ws_log_handler
from rate_limiter import setup_rate_limiting, limiter

# ==========================================
# ENV & APP INIT
# ==========================================

app = FastAPI(
    title="TradingBot API",
    description="Crypto Trading Bot with Tokocrypto and Solana support",
    version="2.0.0",
)

# ==========================================
# RATE LIMITING SETUP
# ==========================================

setup_rate_limiting(app)

# ==========================================
# WEBSOCKET ENDPOINT
# ==========================================

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """
    WebSocket endpoint for real-time updates.
    Clients receive: bot_status, trade_update, system_log, balance_update, solana_status, price_update
    """
    await ws_manager.connect(websocket)
    try:
        # Send initial state on connect
        await websocket.send_json({
            "type": "connected",
            "data": {
                "message": "WebSocket connected",
                "bot_running": IS_BOT_RUNNING,
                "activity": CURRENT_SCAN_TARGET,
            }
        })
        
        # Keep connection alive and handle incoming messages
        while True:
            try:
                # Wait for ping/pong or client messages
                data = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
                # Handle ping
                if data == "ping":
                    await websocket.send_text("pong")
            except asyncio.TimeoutError:
                # Send keepalive ping
                try:
                    await websocket.send_json({"type": "ping"})
                except:
                    break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        pass
    finally:
        await ws_manager.disconnect(websocket)


@app.on_event("startup")
async def startup_event():
    """Install WebSocket log handler on startup."""
    ws_log_handler.install()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    ws_log_handler.uninstall()

# ==========================================
# CORS CONFIGURATION (Secure by Environment)
# ==========================================

def get_cors_origins() -> list:
    """
    Get allowed CORS origins from environment.
    
    - Development: If ALLOWED_ORIGINS is empty or "*", allow all (for local dev only)
    - Production: Parse comma-separated list of allowed origins
    
    Examples:
        ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
        ALLOWED_ORIGINS=https://myapp.example.com,https://admin.example.com
    """
    allowed = os.getenv("ALLOWED_ORIGINS", "").strip()
    env_mode = os.getenv("ENV_MODE", "development").lower()
    
    # In production, require explicit origins
    if env_mode == "production":
        if not allowed or allowed == "*":
            # Default to same-origin only in production if not configured
            sys_logger.log("[CORS] WARNING: No ALLOWED_ORIGINS set in production. Using restrictive default.")
            return ["https://localhost"]
        
        origins = [o.strip() for o in allowed.split(",") if o.strip()]
        sys_logger.log(f"[CORS] Production mode - Allowed origins: {origins}")
        return origins
    
    # Development mode - more permissive
    if not allowed or allowed == "*":
        # Allow common dev origins
        dev_origins = [
            "http://localhost:5173",    # Vite default
            "http://localhost:3000",    # Common React port
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
            "http://localhost:8000",    # FastAPI docs
            "http://127.0.0.1:8000",
        ]
        sys_logger.log(f"[CORS] Development mode - Using default dev origins")
        return dev_origins
    
    # Parse explicit origins for dev
    origins = [o.strip() for o in allowed.split(",") if o.strip()]
    sys_logger.log(f"[CORS] Development mode - Allowed origins: {origins}")
    return origins


# Allowed HTTP methods (restrict in production)
def get_cors_methods() -> list:
    """Get allowed HTTP methods based on environment."""
    env_mode = os.getenv("ENV_MODE", "development").lower()
    
    if env_mode == "production":
        # Only methods actually used by the API
        return ["GET", "POST", "PUT", "DELETE", "OPTIONS"]
    
    return ["*"]  # Allow all in development


# Allowed headers
def get_cors_headers() -> list:
    """Get allowed headers - includes auth headers."""
    return [
        "Content-Type",
        "Authorization",         # JWT Bearer token
        "X-API-Key",            # API key auth
        "X-Request-ID",         # Request tracking
        "Accept",
        "Origin",
        "X-Requested-With",
    ]


CORS_ORIGINS = get_cors_origins()
CORS_METHODS = get_cors_methods()
CORS_HEADERS = get_cors_headers()

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=CORS_METHODS,
    allow_headers=CORS_HEADERS,
    expose_headers=["X-Request-ID", "X-RateLimit-Remaining"],  # Headers client can read
    max_age=600,  # Cache preflight for 10 minutes
)

# ==========================================
# BOT MODE CONFIG
# ==========================================

BOT_MODE = os.getenv("BOT_MODE", "PAPER").upper()
PAPER_INITIAL_BALANCE = float(os.getenv("PAPER_INITIAL_BALANCE", "1000"))

# ==========================================
# RISK MANAGERS (PER-BOT ONLY)
# ==========================================

# Per-bot risk registry with bot-specific profiles and persistence
bot_risk = BotRiskRegistry(PAPER_INITIAL_BALANCE)
hunter_risk = bot_risk.hunter()   # For Tokocrypto Hunter
trader_risk = bot_risk.trader()   # For Solana Trader
sniper_risk = bot_risk.sniper()   # For Solana Sniper

# ==========================================
# FEE CALCULATOR
# ==========================================

fee_calc = fee_calculator.get_calculator(
    exchange_id="tokocrypto",
    slippage_pct=float(os.getenv("SLIPPAGE_PCT", "0.0005")),
)

# ==========================================
# EXCHANGE INIT
# ==========================================

# Support PAPER MODE tanpa credentials
if BOT_MODE == "PAPER":
    # Paper mode - use Binance public API for testing (fallback exchange)
    exchange = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    sys_logger.add_log("📄 PAPER MODE: Using Binance public API for testing")
else:
    # Live mode - requires Tokocrypto credentials
    toko_key = os.getenv("TOKO_API_KEY", "")
    toko_secret = os.getenv("TOKO_SECRET_KEY", "")
    
    if not toko_key or not toko_secret:
        sys_logger.add_log("⚠️ WARNING: No Tokocrypto credentials, using Binance public API")
        BOT_MODE = "PAPER"
    
    # Try Tokocrypto first (if it exists in CCXT), fallback to Binance
    try:
        # Attempt to use Tokocrypto (may fail if not available in this CCXT version)
        exchange = ccxt.tokocrypto({
            "apiKey": toko_key,
            "secret": toko_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })
        sys_logger.add_log("🔌 Connected to Tokocrypto")
    except Exception as e:
        sys_logger.add_log(f"⚠️ Tokocrypto unavailable ({str(e)[:50]}), using Binance")
        exchange = ccxt.binance({
            "apiKey": toko_key,  # Try using same keys
            "secret": toko_secret,
            "enableRateLimit": True,
            "options": {"defaultType": "spot"},
        })


# ==========================================
# GLOBAL STATE
# ==========================================

IS_BOT_RUNNING = False
CURRENT_SCAN_TARGET = "Idle"

# Trailing Stop State (per trade_id)
# {trade_id: {"high_price": float, "trailing_stop": float}}
TRAILING_STOP_STATE = {}
TRAILING_STOP_LOCK = asyncio.Lock()  # Protect concurrent access

# Trailing Stop Config
TRAILING_STOP_ACTIVATION_PCT = 0.01   # Activate after 1% profit
TRAILING_STOP_DISTANCE_PCT = 0.015    # Trail 1.5% behind high

# ==========================================
# MODELS
# ==========================================

class TradeSignal(BaseModel):
    symbol: str
    action: str

class SwapRequest(BaseModel):
    amount: float
    input_token: str = "SOL"
    output_token: str = "USDC"

# ==========================================
# DATABASE HELPERS (USING ATOMIC TRADE LIFECYCLE)
# ==========================================

def get_any_active_trade():
    """Get any trade in OPEN or CLOSING state."""
    session = get_db_session()
    try:
        trade = session.query(Trade).filter(
            Trade.status.in_([TradeState.OPEN, TradeState.CLOSING])
        ).first()
        return trade
    finally:
        session.close()


def get_all_active_trades():
    """Get all trades in OPEN or CLOSING state."""
    session = get_db_session()
    try:
        trades = session.query(Trade).filter(
            Trade.status.in_([TradeState.OPEN, TradeState.CLOSING])
        ).all()
        return trades
    finally:
        session.close()


# ==========================================
# POSITION CLEANUP ON BOT STOP
# ==========================================

# Configuration for position handling on stop
# Options: "warn", "force_close", "persist"
# - "warn": Log warning about open positions (default)
# - "force_close": Close all positions at market price
# - "persist": Keep positions in DB for resume on restart
BOT_STOP_POSITION_ACTION = os.getenv("BOT_STOP_POSITION_ACTION", "warn").lower()


async def cleanup_open_positions(action: str = None, force_price: dict = None):
    """
    Handle open positions when bot stops.
    
    Args:
        action: Override action ("warn", "force_close", "persist")
        force_price: Dict of {symbol: price} for force closing without fetching
    
    Returns:
        dict with cleanup results
    """
    action = action or BOT_STOP_POSITION_ACTION
    active_trades = get_all_active_trades()
    
    if not active_trades:
        sys_logger.add_log("✅ No open positions to handle")
        return {"status": "clean", "positions": 0}
    
    result = {
        "status": "processed",
        "action": action,
        "positions": len(active_trades),
        "details": []
    }
    
    sys_logger.add_log(f"⚠️ Found {len(active_trades)} open position(s) on bot stop")
    
    for trade in active_trades:
        trade_info = {
            "id": trade.id,
            "symbol": trade.symbol,
            "buy_price": trade.buy_price,
            "amount": trade.amount,
            "status": trade.status.value if hasattr(trade.status, 'value') else str(trade.status),
        }
        
        if action == "warn":
            # Just log warning, don't touch positions
            sys_logger.add_log(f"⚠️ ORPHANED POSITION: {trade.symbol} | Amount: {trade.amount:.6f} | Entry: ${trade.buy_price:.4f}")
            trade_info["action"] = "warned"
            
        elif action == "force_close":
            # Force close at market price
            try:
                if force_price and trade.symbol in force_price:
                    current_price = force_price[trade.symbol]
                else:
                    ticker = await exchange.fetch_ticker(trade.symbol)
                    current_price = ticker["last"]
                
                profit = (current_price - trade.buy_price) * trade.amount
                pnl_pct = ((current_price - trade.buy_price) / trade.buy_price) * 100
                
                # Execute sell if in LIVE mode
                if BOT_MODE == "LIVE":
                    sell_result = await execution.safe_execute_order(
                        exchange, trade.symbol, "sell", trade.amount * current_price,
                        max_slippage_pct=2.0,  # Higher tolerance for emergency close
                        check_liquidity_first=False
                    )
                    if not sell_result["success"]:
                        sys_logger.add_log(f"❌ Force close failed for {trade.symbol}: {sell_result.get('error')}")
                        trade_info["action"] = "failed"
                        trade_info["error"] = sell_result.get("error")
                        result["details"].append(trade_info)
                        continue
                
                # Update database
                save_sell_trade(trade.id, current_price, profit, reason="BOT_STOP_FORCE_CLOSE")
                hunter_risk.record_trade_pnl(profit)
                
                sys_logger.add_log(f"🔴 FORCE CLOSED: {trade.symbol} | Price: ${current_price:.4f} | PnL: ${profit:.2f} ({pnl_pct:+.2f}%)")
                trade_info["action"] = "force_closed"
                trade_info["exit_price"] = current_price
                trade_info["profit"] = profit
                trade_info["pnl_pct"] = pnl_pct
                
            except Exception as e:
                sys_logger.add_log(f"❌ Error force closing {trade.symbol}: {e}")
                trade_info["action"] = "error"
                trade_info["error"] = str(e)
                
        elif action == "persist":
            # Mark as persisted (will resume on restart)
            sys_logger.add_log(f"💾 PERSISTED: {trade.symbol} | Will resume management on restart")
            trade_info["action"] = "persisted"
            # Position remains in OPEN state in DB
            
        result["details"].append(trade_info)
    
    # Summary log
    if action == "warn":
        sys_logger.add_log(f"⚠️ WARNING: {len(active_trades)} position(s) left unmanaged! Manual intervention may be required.")
    elif action == "force_close":
        closed = sum(1 for d in result["details"] if d.get("action") == "force_closed")
        sys_logger.add_log(f"🔴 Force closed {closed}/{len(active_trades)} positions")
    elif action == "persist":
        sys_logger.add_log(f"💾 {len(active_trades)} position(s) persisted for resume on restart")
    
    return result


async def emergency_close_all_positions():
    """
    Emergency function to close all open positions immediately.
    Called via API endpoint for manual intervention.
    """
    sys_logger.add_log("🚨 EMERGENCY CLOSE ALL triggered")
    return await cleanup_open_positions(action="force_close")


def save_buy_trade(symbol, price, amount, usdt, bot_type="HUNTER"):
    """
    Create and immediately open a trade using atomic lifecycle.
    Returns trade_id.
    
    Converts numpy types to Python native types for PostgreSQL compatibility.
    """
    # Convert numpy types to Python native types (np.float64 -> float)
    if HAS_NUMPY:
        price = float(price) if isinstance(price, (np.floating, np.integer)) else price
        amount = float(amount) if isinstance(amount, (np.floating, np.integer)) else amount
        usdt = float(usdt) if isinstance(usdt, (np.floating, np.integer)) else usdt
    
    with session_scope() as session:
        # Create trade in PENDING state
        trade = Trade(
            symbol=symbol,
            side='BUY',
            buy_price=price,
            amount=amount,
            total_usdt=usdt,
            status=TradeState.PENDING,
            mode=BOT_MODE,
            bot_type=bot_type
        )
        session.add(trade)
        session.flush()
        trade_id = trade.id
        
        # Log creation
        ledger = TradeLedger(
            trade_id=trade_id,
            event_type='CREATED',
            new_state=TradeState.PENDING,
            price=price,
            amount=amount,
            value_usdt=usdt,
            bot_type=bot_type,
            reason='NEW_ORDER'
        )
        session.add(ledger)
        
        # Immediately transition to OPEN
        trade.status = TradeState.OPEN
        from datetime import datetime
        trade.opened_at = datetime.utcnow()
        
        ledger_open = TradeLedger(
            trade_id=trade_id,
            event_type='OPENED',
            old_state=TradeState.PENDING,
            new_state=TradeState.OPEN,
            price=price,
            reason='ORDER_FILLED'
        )
        session.add(ledger_open)
    
    # Broadcast trade update via WebSocket
    try:
        import asyncio
        asyncio.create_task(ws_manager.broadcast_trade_update({
            "id": trade_id,
            "symbol": symbol,
            "side": "BUY",
            "buy_price": price,
            "amount": amount,
            "total_usdt": usdt,
            "status": "OPEN",
            "bot_type": bot_type,
        }))
    except RuntimeError:
        pass  # No event loop
    
    return trade_id

def save_sell_trade(trade_id, sell_price, profit, reason="TP_HIT"):
    """
    Close a trade using atomic lifecycle with ledger logging.
    
    Converts numpy types to Python native types for PostgreSQL compatibility.
    """
    # Convert numpy types to Python native types
    if HAS_NUMPY:
        sell_price = float(sell_price) if isinstance(sell_price, (np.floating, np.integer)) else sell_price
        profit = float(profit) if isinstance(profit, (np.floating, np.integer)) else profit
    
    with session_scope() as session:
        trade = session.query(Trade).filter_by(id=trade_id).first()
        if not trade:
            return False
        
        from datetime import datetime
        
        # Start closing
        trade.status = TradeState.CLOSING
        trade.closing_at = datetime.utcnow()
        trade.sell_price = sell_price
        trade.profit_usdt = profit
        
        ledger_closing = TradeLedger(
            trade_id=trade_id,
            event_type='CLOSING',
            old_state=TradeState.OPEN,
            new_state=TradeState.CLOSING,
            price=sell_price,
            reason=reason
        )
        session.add(ledger_closing)
        
        # Complete the close
        trade.status = TradeState.CLOSED
        trade.closed_at = datetime.utcnow()
        
        ledger_closed = TradeLedger(
            trade_id=trade_id,
            event_type='CLOSED',
            old_state=TradeState.CLOSING,
            new_state=TradeState.CLOSED,
            price=sell_price,
            pnl=profit,
            reason=reason
        )
        session.add(ledger_closed)
    
    # Broadcast trade update via WebSocket
    try:
        import asyncio
        asyncio.create_task(ws_manager.broadcast_trade_update({
            "id": trade_id,
            "side": "SELL",
            "sell_price": sell_price,
            "profit_usdt": profit,
            "status": "CLOSED",
            "reason": reason,
        }))
    except RuntimeError:
        pass  # No event loop
    
    return True

# ==========================================
# MARKET SCANNER
# ==========================================

async def get_top_liquid_coins(limit=10):
    """Fetch top liquid coins from exchange with fallback."""
    try:
        tickers = await exchange.fetch_tickers()
        pairs = []

        for symbol, data in tickers.items():
            if "USDT" not in symbol:
                continue

            vol = float(data.get("quoteVolume") or 0)
            clean = symbol.replace("_", "/")

            if "/" not in clean:
                continue

            base, quote = clean.split("/")
            if quote != "USDT":
                continue

            pairs.append({"symbol": clean, "volume": vol})

        pairs.sort(key=lambda x: x["volume"], reverse=True)
        result = [p["symbol"] for p in pairs[:limit]] or ["BTC/USDT", "ETH/USDT"]
        sys_logger.add_log(f"📊 Scanned {len(pairs)} pairs, top {len(result)} selected")
        return result

    except Exception as e:
        error_type = execution.classify_error(e)
        sys_logger.add_log(f"⚠️ [GET_COINS] {error_type}: {str(e)[:80]}")
        # Fallback to common pairs when exchange API fails
        return ["BTC/USDT", "ETH/USDT", "BNB/USDT", "XRP/USDT", "ADA/USDT"]

# ==========================================
# BOT LOOP (HUNTER)
# ==========================================

async def auto_trading_loop():
    global CURRENT_SCAN_TARGET

    sys_logger.add_log("🚀 Hunter Bot Loop Started")

    try:
        await exchange.load_markets()
    except:
        pass

    TP = 0.025  # 2.5% take profit
    SL = 0.02   # 2% stop loss (ratio 1.25:1, need ~44.44% win rate)
    
    # P4: Dynamic position sizing based on volatility
    BASE_TRADE_USDT = 12.0   # Minimum/base position
    MAX_TRADE_USDT = 50.0    # Maximum cap
    BASE_RISK_PCT = 2.0      # Base risk per trade

    try:
        while IS_BOT_RUNNING:
            # ========== KILL SWITCH CHECK ==========
            if not kill_switch.is_trading_allowed():
                CURRENT_SCAN_TARGET = "⛔ KILL SWITCH ACTIVE"
                sys_logger.add_log("⛔ Trading blocked by kill switch")
                await asyncio.sleep(30)  # Check again in 30 seconds
                continue
            
            # ========== HUNTER RISK CHECK ==========
            if not hunter_risk.can_trade_new():
                if hunter_risk.is_in_cooldown():
                    remaining = hunter_risk.get_cooldown_remaining()
                    CURRENT_SCAN_TARGET = f"⏸️ Cooldown ({remaining}s)"
                    sys_logger.add_log(f"⏸️ Hunter in cooldown: {remaining}s remaining")
                else:
                    CURRENT_SCAN_TARGET = "⚠️ Risk limit reached"
                    sys_logger.add_log("⚠️ Hunter trading halted by risk manager")
                await asyncio.sleep(10)
                continue
            
            active = get_any_active_trade()

            # ======================
            # MANAGE OPEN POSITION (WITH TRAILING STOP)
            # ======================
            if active:
                symbol = active.symbol
                trade_id = active.id
                CURRENT_SCAN_TARGET = f"Managing {symbol}"

                try:
                    ticker = await exchange.fetch_ticker(symbol)
                    price = ticker["last"]

                    buy_price = active.buy_price
                    amount = active.amount

                    pnl_pct = (price - buy_price) / buy_price
                    
                    # ========== TRAILING STOP LOGIC ==========
                    exit_reason = None
                    should_exit = False
                    
                    # Initialize trailing stop state for this trade (with lock)
                    async with TRAILING_STOP_LOCK:
                        if trade_id not in TRAILING_STOP_STATE:
                            TRAILING_STOP_STATE[trade_id] = {
                                "high_price": price,
                                "trailing_active": False
                            }
                        
                        ts_state = TRAILING_STOP_STATE[trade_id]
                        
                        # Update high water mark
                        if price > ts_state["high_price"]:
                            ts_state["high_price"] = price
                        
                        # Activate trailing stop when profit reaches threshold
                        if pnl_pct >= TRAILING_STOP_ACTIVATION_PCT:
                            ts_state["trailing_active"] = True
                            trailing_stop_price = ts_state["high_price"] * (1 - TRAILING_STOP_DISTANCE_PCT)
                            
                            # Check if trailing stop hit
                            if price <= trailing_stop_price:
                                should_exit = True
                                exit_reason = "TRAILING_STOP"
                    
                    # Regular TP/SL still applies
                    if pnl_pct >= TP:
                        should_exit = True
                        exit_reason = "TP_HIT"
                    elif pnl_pct <= -SL:
                        should_exit = True
                        exit_reason = "SL_HIT"
                    
                    # Execute exit if needed
                    if should_exit and exit_reason:
                        profit = (price - buy_price) * amount

                        if BOT_MODE == "LIVE":
                            # P3: Use safe execution with retry
                            result = await execution.safe_execute_order(
                                exchange, symbol, "sell", amount * price,
                                max_slippage_pct=1.0, check_liquidity_first=True
                            )
                            if not result["success"]:
                                sys_logger.add_log(f"⚠️ Sell failed: {result.get('error')}")
                                continue

                        save_sell_trade(active.id, price, profit, reason=exit_reason)
                        hunter_risk.record_trade_pnl(profit)
                        
                        # Cleanup trailing stop state (with lock)
                        async with TRAILING_STOP_LOCK:
                            if trade_id in TRAILING_STOP_STATE:
                                del TRAILING_STOP_STATE[trade_id]
                        
                        sys_logger.add_log(f"📊 Trade closed: {symbol} | {exit_reason} | PnL: ${profit:.2f}")

                    await asyncio.sleep(2)

                except Exception as e:
                    error_type = execution.classify_error(e)
                    print(f"[MANAGE ERROR] {error_type}: {e}")

            # ======================
            # SCAN NEW TRADE
            # ======================
            else:
                if not hunter_risk.can_trade_new():
                    CURRENT_SCAN_TARGET = "Risk Limit Hit"
                    await asyncio.sleep(30)
                    continue

                for symbol in await get_top_liquid_coins():
                    if not IS_BOT_RUNNING:
                        break

                    CURRENT_SCAN_TARGET = f"Scanning {symbol}"

                    try:
                        # P3: Check spread before analyzing
                        spread_ok, spread_info = await execution.check_spread(exchange, symbol, max_spread_pct=0.5)
                        if not spread_ok:
                            sys_logger.add_log(f"⏭️ Skip {symbol}: high spread {spread_info.get('spread_pct', 0):.2f}%")
                            continue
                        
                        signal, price, indicators = await strategy.analyze_market(exchange, symbol)
                        
                        # P4: Calculate ATR-based dynamic position size
                        atr_pct = indicators.get('atr_pct', 2.0)  # Default 2% if not available
                        portfolio_value = hunter_risk.current_balance
                        
                        sizing = strategy.calculate_atr_position_size(
                            base_risk_pct=BASE_RISK_PCT,
                            atr_pct=atr_pct,
                            portfolio_value=portfolio_value,
                            entry_price=price
                        )
                        
                        # Clamp position value between min and max
                        TRADE_USDT = max(BASE_TRADE_USDT, min(MAX_TRADE_USDT, sizing.get('position_value', BASE_TRADE_USDT)))
                        
                        # Log all signals (BUY, SELL, HOLD) for frontend display
                        if signal == "BUY":
                            action_msg = "BUY"
                            reason = indicators.get('reason', 'Signal detected')
                            strategy_type = indicators.get('strategy', 'UNKNOWN')
                            htf = indicators.get('htf_signal', 'NEUTRAL')
                            vol_factor = sizing.get('volatility_factor', 1.0)
                            sys_logger.add_log(f"📊 {symbol} | {strategy_type} | {reason} | HTF:{htf} -> {action_msg}")
                            sys_logger.add_log(f"💰 Size: ${TRADE_USDT:.2f} | ATR:{atr_pct:.2f}% | VolFactor:{vol_factor:.2f}x")
                        elif signal == "SELL":
                            reason = indicators.get('reason', 'Signal detected')
                            strategy_type = indicators.get('strategy', 'UNKNOWN')
                            htf = indicators.get('htf_signal', 'NEUTRAL')
                            sys_logger.add_log(f"📊 {symbol} | {strategy_type} | {reason} | HTF:{htf} -> SELL")
                        
                        if signal != "BUY":
                            continue

                        amount = TRADE_USDT / price
                        
                        # P3: Check liquidity before buy
                        is_liquid, liquidity = await execution.check_liquidity(
                            exchange, symbol, TRADE_USDT, "buy", max_slippage_pct=0.5
                        )
                        if not is_liquid:
                            sys_logger.add_log(f"⏭️ Skip {symbol}: low liquidity")
                            continue

                        if BOT_MODE == "LIVE":
                            # P3: Use safe execution with retry
                            result = await execution.safe_execute_order(
                                exchange, symbol, "buy", TRADE_USDT,
                                max_slippage_pct=0.5, check_liquidity_first=False  # Already checked
                            )
                            if not result["success"]:
                                sys_logger.add_log(f"❌ Buy failed: {result.get('error')}")
                                continue

                        save_buy_trade(symbol, price, amount, TRADE_USDT)
                        break

                    except Exception as e:
                        error_type = execution.classify_error(e)
                        print(f"[SCAN ERROR] {symbol} {error_type}: {e}")

                    await asyncio.sleep(1)

            await asyncio.sleep(1)

    except Exception as e:
        sys_logger.add_log(f"💥 Bot loop crashed: {type(e).__name__}: {str(e)[:100]}")
        raise
    finally:
        # ========== HANDLE OPEN POSITIONS ==========
        sys_logger.add_log("🛑 Bot stopping - checking open positions...")
        try:
            cleanup_result = await cleanup_open_positions()
            if cleanup_result["positions"] > 0:
                sys_logger.add_log(f"📋 Position cleanup: {cleanup_result['action']} - {cleanup_result['positions']} position(s)")
        except Exception as cleanup_err:
            sys_logger.add_log(f"⚠️ Error during position cleanup: {cleanup_err}")
        
        # ========== CLOSE EXCHANGE CONNECTION ==========
        sys_logger.add_log("🔌 Closing exchange connection...")
        try:
            await exchange.close()
            sys_logger.add_log("✅ Exchange connection closed")
        except Exception as close_err:
            sys_logger.add_log(f"⚠️ Error closing exchange: {close_err}")

# ==========================================
# ROUTER IMPORTS AND MOUNTING
# ==========================================

from routes import (
    bot_router, paper_router, solana_router, risk_router,
    backtest_router, analytics_router, fee_router, system_router
)
from auth import auth_router

# Mount all routers
app.include_router(auth_router)  # Auth endpoints first
app.include_router(bot_router)
app.include_router(paper_router)
app.include_router(solana_router)
app.include_router(risk_router)
app.include_router(backtest_router)
app.include_router(analytics_router)
app.include_router(fee_router)
app.include_router(system_router)
