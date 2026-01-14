# ==========================================
# File: backend/main.py
# ==========================================

import os
import asyncio
import ccxt.async_support as ccxt
from dotenv import load_dotenv
from fastapi import FastAPI, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

# ==========================================
# ENV & APP INIT
# ==========================================

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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

def save_buy_trade(symbol, price, amount, usdt, bot_type="HUNTER"):
    """
    Create and immediately open a trade using atomic lifecycle.
    Returns trade_id.
    
    Converts numpy types to Python native types for PostgreSQL compatibility.
    """
    # Convert numpy types to Python native types (np.float64 -> float)
    import numpy as np
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
    
    return trade_id

def save_sell_trade(trade_id, sell_price, profit, reason="TP_HIT"):
    """
    Close a trade using atomic lifecycle with ledger logging.
    
    Converts numpy types to Python native types for PostgreSQL compatibility.
    """
    # Convert numpy types to Python native types
    import numpy as np
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
        sys_logger.add_log("🔌 Closing exchange connection...")
        try:
            await exchange.close()
            sys_logger.add_log("✅ Exchange connection closed")
        except Exception as close_err:
            sys_logger.add_log(f"⚠️ Error closing exchange: {close_err}")

# ==========================================
# API ENDPOINTS
# ==========================================

@app.get("/")
def home():
    return {"status": "ready"}

@app.post("/api/bot/toggle")
async def toggle_bot(bg: BackgroundTasks):
    global IS_BOT_RUNNING

    IS_BOT_RUNNING = not IS_BOT_RUNNING

    if IS_BOT_RUNNING:
        bg.add_task(auto_trading_loop)
        return {"status": "running"}
    return {"status": "stopped"}

@app.get("/api/bot/status")
def bot_status():
    return {
        "is_running": IS_BOT_RUNNING,
        "current_activity": CURRENT_SCAN_TARGET,
        "running": IS_BOT_RUNNING,  # Legacy
        "activity": CURRENT_SCAN_TARGET,  # Legacy
    }

@app.get("/api/trade/history")
def trade_history():
    session = get_db_session()
    try:
        trades = session.query(Trade).order_by(Trade.id.desc()).limit(50).all()
        return [
            {
                'id': t.id,
                'symbol': t.symbol,
                'side': t.side,
                'buy_price': t.buy_price,
                'sell_price': t.sell_price,
                'amount': t.amount,
                'total_usdt': t.total_usdt,
                'status': t.status,
                'profit_usdt': t.profit_usdt,
                'created_at': t.created_at.isoformat() if t.created_at else None,
                'entry_time': t.created_at.isoformat() if t.created_at else None,
                'exit_time': t.closed_at.isoformat() if t.closed_at else None,
                'bot_type': t.bot_type,
                'mode': t.mode,
                'source': 'Hunter',  # Add source field for frontend
            }
            for t in trades
        ]
    finally:
        session.close()

@app.get("/api/trade/ledger")
def trade_ledger(trade_id: int = None, bot_type: str = None, limit: int = 100):
    """
    Get immutable trade ledger entries.
    Filter by trade_id or bot_type.
    """
    session = get_db_session()
    try:
        query = session.query(TradeLedger)
        if trade_id:
            query = query.filter(TradeLedger.trade_id == trade_id)
        if bot_type:
            query = query.filter(TradeLedger.bot_type == bot_type)
        entries = query.order_by(TradeLedger.timestamp.desc()).limit(limit).all()
        return [
            {
                'id': e.id,
                'trade_id': e.trade_id,
                'event_type': e.event_type,
                'old_state': e.old_state,
                'new_state': e.new_state,
                'price': e.price,
                'amount': e.amount,
                'pnl': e.pnl,
                'reason': e.reason,
                'timestamp': e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in entries
        ]
    finally:
        session.close()

@app.get("/api/trade/ledger/{trade_id}")
def trade_ledger_by_id(trade_id: int):
    """Get all ledger entries for a specific trade."""
    session = get_db_session()
    try:
        entries = session.query(TradeLedger).filter(TradeLedger.trade_id == trade_id).order_by(TradeLedger.timestamp).all()
        return [
            {
                'id': e.id,
                'trade_id': e.trade_id,
                'event_type': e.event_type,
                'old_state': e.old_state,
                'new_state': e.new_state,
                'price': e.price,
                'amount': e.amount,
                'pnl': e.pnl,
                'reason': e.reason,
                'timestamp': e.timestamp.isoformat() if e.timestamp else None,
            }
            for e in entries
        ]
    finally:
        session.close()

# ==========================================
# SOLANA ENDPOINTS
# ==========================================

@app.get("/api/solana/balance")
async def sol_balance():
    return await jupiter_bot.get_token_balances()

@app.get("/api/solana/history")
def sol_history():
    return solana_tracker.load_history()

# ==========================================
# GLOBAL KILL SWITCH ENDPOINTS
# ==========================================

@app.get("/api/killswitch/status")
def killswitch_status():
    """Get current kill switch status and limits."""
    return kill_switch.get_status()

@app.post("/api/killswitch/toggle")
def killswitch_toggle(enabled: bool = True):
    """Enable or disable manual kill switch."""
    success = kill_switch.set_manual_kill(enabled)
    return {
        "success": success,
        "manual_kill_enabled": enabled,
        "trading_allowed": kill_switch.is_trading_allowed()
    }

@app.get("/api/killswitch/check")
def killswitch_check():
    """Quick check if trading is allowed."""
    return {"trading_allowed": kill_switch.is_trading_allowed()}

# ==========================================
# PER-BOT RISK STATUS ENDPOINTS
# ==========================================

@app.get("/api/risk/bots")
def risk_all_bots():
    """Get risk status for all bots (Hunter, Trader, Sniper)."""
    return bot_risk.get_all_status()

@app.get("/api/risk/hunter")
def risk_hunter():
    """Get Hunter bot risk status."""
    return {
        "bot_type": "HUNTER",
        "can_trade": hunter_risk.is_trading_allowed,
        "daily_pnl": hunter_risk.daily_pnl,
        "trades_today": hunter_risk.trades_today,
        "in_cooldown": hunter_risk.is_in_cooldown(),
        "cooldown_remaining": hunter_risk.get_cooldown_remaining(),
        "consecutive_losses": hunter_risk.consecutive_losses,
        "limits": hunter_risk.limits.dict()
    }

@app.get("/api/risk/trader")
def risk_trader():
    """Get Trader bot risk status."""
    return {
        "bot_type": "TRADER",
        "can_trade": trader_risk.is_trading_allowed,
        "daily_pnl": trader_risk.daily_pnl,
        "trades_today": trader_risk.trades_today,
        "in_cooldown": trader_risk.is_in_cooldown(),
        "cooldown_remaining": trader_risk.get_cooldown_remaining(),
        "consecutive_losses": trader_risk.consecutive_losses,
        "limits": trader_risk.limits.dict()
    }

@app.get("/api/risk/sniper")
def risk_sniper():
    """Get Sniper bot risk status."""
    return {
        "bot_type": "SNIPER",
        "can_trade": sniper_risk.is_trading_allowed,
        "daily_pnl": sniper_risk.daily_pnl,
        "trades_today": sniper_risk.trades_today,
        "in_cooldown": sniper_risk.is_in_cooldown(),
        "cooldown_remaining": sniper_risk.get_cooldown_remaining(),
        "consecutive_losses": sniper_risk.consecutive_losses,
        "limits": sniper_risk.limits.dict()
    }

# ==========================================
# PAPER TRADING
# ==========================================

@app.get("/api/paper/account")
async def paper_account():
    prices = {}
    for s in paper_trading.paper_account.positions:
        try:
            ticker = await exchange.fetch_ticker(s)
            prices[s] = ticker["last"]
        except:
            pass
    return paper_trading.paper_account.get_account_summary(prices)


class PaperBuyRequest(BaseModel):
    symbol: str
    amount_usdt: float


class PaperSellRequest(BaseModel):
    symbol: str
    percentage: float = 100


@app.post("/api/paper/buy")
async def paper_buy(req: PaperBuyRequest):
    """Execute paper buy order."""
    try:
        # Get current price
        ticker = await exchange.fetch_ticker(req.symbol)
        price = ticker["last"]
    except Exception as e:
        return {"status": "failed", "reason": f"Failed to fetch price: {e}"}
    
    # Check risk before buy
    open_positions = len(paper_trading.paper_account.positions)
    wallet_balance = paper_trading.paper_account.balance
    risk_check = hunter_risk.can_open_position(open_positions, wallet_balance, req.amount_usdt)
    
    if not risk_check.get("approved", False):
        return {"status": "rejected", "reasons": risk_check.get("reasons", ["Risk check failed"])}
    
    result = paper_trading.paper_account.place_market_buy(
        req.symbol, req.amount_usdt, price
    )
    return result


@app.post("/api/paper/sell")
async def paper_sell(req: PaperSellRequest):
    """Execute paper sell order."""
    try:
        ticker = await exchange.fetch_ticker(req.symbol)
        price = ticker["last"]
    except Exception as e:
        return {"status": "failed", "reason": f"Failed to fetch price: {e}"}
    
    result = paper_trading.paper_account.place_market_sell(
        req.symbol, req.percentage, price
    )
    return result


@app.post("/api/paper/reset")
async def paper_reset():
    """Reset paper trading account."""
    paper_trading.paper_account.reset_account(PAPER_INITIAL_BALANCE)
    return {"status": "reset", "balance": PAPER_INITIAL_BALANCE}


@app.get("/api/paper/orders")
async def paper_orders():
    """Get paper trading order history."""
    return paper_trading.paper_account.orders_history


@app.get("/api/paper/trades")
async def paper_trades():
    """Get paper trading trade history."""
    return paper_trading.paper_account.trades_history


# ==========================================
# BOT MODE
# ==========================================

@app.get("/api/bot/mode")
async def bot_mode():
    """Get current bot mode (LIVE/PAPER/BACKTEST)."""
    return {"mode": BOT_MODE}


# ==========================================
# FEE CALCULATOR
# ==========================================

class FeeCalcRequest(BaseModel):
    amount: float
    price: float
    is_maker: bool = False


@app.post("/api/fee/calculate-buy")
async def fee_calculate_buy(req: FeeCalcRequest):
    """Calculate buy fees."""
    order_type = 'limit' if req.is_maker else 'market'
    result = fee_calc.calculate_buy_cost(req.amount, req.price, order_type)
    return result


@app.post("/api/fee/calculate-sell")
async def fee_calculate_sell(req: FeeCalcRequest):
    """Calculate sell fees."""
    order_type = 'limit' if req.is_maker else 'market'
    result = fee_calc.calculate_sell_proceeds(req.amount, req.price, order_type)
    return result


class RoundTripRequest(BaseModel):
    amount: float
    buy_price: float
    sell_price: float = None
    is_maker: bool = False


@app.post("/api/fee/round-trip")
async def fee_round_trip(req: RoundTripRequest):
    """Calculate round-trip (buy+sell) fees and profit."""
    result = fee_calc.calculate_round_trip_cost(req.amount, req.buy_price)
    return result


class ProfitTargetRequest(BaseModel):
    amount: float
    entry_price: float
    target_profit_pct: float
    is_maker: bool = False


@app.post("/api/fee/profit-target")
async def fee_profit_target(req: ProfitTargetRequest):
    """Calculate price needed to hit profit target after fees."""
    result = fee_calc.calculate_profit_target(
        req.entry_price, req.amount, req.target_profit_pct
    )
    return result


# ==========================================
# RISK MANAGEMENT ENDPOINTS
# ==========================================

class PositionSizeRequest(BaseModel):
    entry_price: float
    stop_loss_price: float
    portfolio_value: float = None


@app.post("/api/risk/position-size")
async def risk_position_size(req: PositionSizeRequest):
    """Calculate optimal position size based on risk."""
    portfolio = req.portfolio_value or hunter_risk.current_balance
    size = hunter_risk.calculate_position_size(
        portfolio, req.entry_price, req.stop_loss_price
    )
    return {
        "position_size": size,
        "portfolio_value": portfolio,
        "risk_per_trade_pct": hunter_risk.limits.risk_per_trade_pct,
    }


@app.get("/api/risk/summary")
async def risk_summary():
    """Get current risk summary."""
    # Try to get current equity from paper trading
    try:
        prices = {}
        for s in paper_trading.paper_account.positions:
            try:
                prices[s] = (await exchange.fetch_ticker(s))["last"]
            except:
                pass
        summary = paper_trading.paper_account.get_account_summary(prices)
        current_equity = summary.get("total_equity", hunter_risk.current_balance)
    except:
        current_equity = hunter_risk.current_balance
    
    open_positions = len(paper_trading.paper_account.positions) if paper_trading.paper_account else 0
    return hunter_risk.get_risk_summary(current_equity, open_positions)


@app.get("/api/risk/kelly")
async def risk_kelly():
    """Calculate Kelly criterion position size."""
    # Get historical win rate from trades
    session = get_db_session()
    try:
        trades_obj = session.query(Trade).filter(Trade.status == TradeState.CLOSED).order_by(Trade.id.desc()).limit(100).all()
        trades = [{'profit_usdt': t.profit_usdt} for t in trades_obj]
    finally:
        session.close()
    
    if not trades:
        return {"kelly_pct": 0, "message": "No trade history"}
    
    wins = sum(1 for t in trades if t.get("profit_usdt", 0) > 0)
    win_rate = wins / len(trades) if trades else 0.5
    
    # Calculate average win/loss ratio
    winning_trades = [t for t in trades if t.get("profit_usdt", 0) > 0]
    losing_trades = [t for t in trades if t.get("profit_usdt", 0) < 0]
    
    avg_win = sum(t.get("profit_usdt", 0) for t in winning_trades) / len(winning_trades) if winning_trades else 1
    avg_loss = abs(sum(t.get("profit_usdt", 0) for t in losing_trades) / len(losing_trades)) if losing_trades else 1
    
    win_loss_ratio = avg_win / avg_loss if avg_loss > 0 else 1
    
    # Kelly formula: K% = W - [(1-W)/R]
    kelly = win_rate - ((1 - win_rate) / win_loss_ratio) if win_loss_ratio > 0 else 0
    kelly = max(0, min(kelly, 0.25))  # Cap at 25%
    
    return {
        "kelly_pct": round(kelly * 100, 2),
        "win_rate": round(win_rate * 100, 2),
        "win_loss_ratio": round(win_loss_ratio, 2),
        "trades_analyzed": len(trades),
    }


# ==========================================
# BACKTEST ENDPOINTS
# ==========================================

class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = "RSI_MACD"
    start_date: str = None
    end_date: str = None
    initial_capital: float = 1000
    timeframe: str = "1m"


@app.post("/api/backtest/run")
async def backtest_run(req: BacktestRequest):
    """Run a backtest."""
    try:
        result = await backtesting.run_backtest(
            symbol=req.symbol,
            strategy=req.strategy,
            start_date=req.start_date,
            end_date=req.end_date,
            initial_capital=req.initial_capital,
            timeframe=req.timeframe,
        )
        # Save result to PostgreSQL
        from database_pg import BacktestResult
        import json
        with session_scope() as session:
            backtest = BacktestResult(
                symbol=result['symbol'],
                timeframe=result['timeframe'],
                period_days=result.get('period_days', 30),
                initial_capital=result['initial_capital'],
                final_capital=result['final_capital'],
                roi_pct=result['roi_pct'],
                total_trades=result['total_trades'],
                win_rate_pct=result['win_rate_pct'],
                max_drawdown_pct=result['max_drawdown_pct'],
                profit_factor=result['profit_factor'],
                total_fees_paid=result.get('total_fees_paid', 0),
                result_json=json.dumps(result, default=str)
            )
            session.add(backtest)
        return result
    except Exception as e:
        return {"error": str(e)}


class BatchBacktestRequest(BaseModel):
    symbols: list
    strategy: str = "RSI_MACD"
    initial_capital: float = 1000


@app.post("/api/backtest/batch")
async def backtest_batch(req: BatchBacktestRequest):
    """Run batch backtest on multiple symbols."""
    results = []
    for symbol in req.symbols:
        try:
            result = await backtesting.run_backtest(
                symbol=symbol,
                strategy=req.strategy,
                initial_capital=req.initial_capital,
            )
            results.append(result)
        except Exception as e:
            results.append({"symbol": symbol, "error": str(e)})
    return {"results": results}


@app.get("/api/backtest/history")
async def backtest_history():
    """Get backtest history."""
    from database_pg import BacktestResult
    session = get_db_session()
    try:
        results = session.query(BacktestResult).order_by(BacktestResult.created_at.desc()).limit(10).all()
        return {
            "history": [
                {
                    'id': r.id,
                    'symbol': r.symbol,
                    'timeframe': r.timeframe,
                    'roi_pct': r.roi_pct,
                    'total_trades': r.total_trades,
                    'win_rate_pct': r.win_rate_pct,
                    'max_drawdown_pct': r.max_drawdown_pct,
                    'profit_factor': r.profit_factor,
                    'created_at': r.created_at.isoformat() if r.created_at else None,
                }
                for r in results
            ]
        }
    finally:
        session.close()


# ==========================================
# SOLANA ENDPOINTS
# ==========================================

class QuoteRequest(BaseModel):
    input_token: str = "SOL"
    output_token: str
    amount: float
    slippage_bps: int = 100


@app.post("/api/solana/quote")
async def solana_quote(req: QuoteRequest):
    """Get Jupiter swap quote."""
    quote = await jupiter_bot.get_quote(
        req.input_token, req.output_token, req.amount, req.slippage_bps
    )
    return quote


class SwapRequest(BaseModel):
    quote_response: dict


@app.post("/api/solana/swap")
async def solana_swap(req: SwapRequest):
    """Execute Jupiter swap."""
    result = await jupiter_bot.execute_swap(req.quote_response)
    return result


@app.post("/api/solana/auto/toggle")
async def solana_auto_toggle(background_tasks: BackgroundTasks):
    """Toggle Solana auto trading bot."""
    if solana_auto.is_running:
        solana_auto.stop()
        return {"status": "stopped"}
    else:
        background_tasks.add_task(solana_auto.start, "AUTO_HUNT")
        return {"status": "started"}


@app.get("/api/solana/auto/status")
async def solana_auto_status():
    """Get Solana auto bot status."""
    return {
        "is_running": solana_auto.is_running,
        "mode": solana_auto.mode,
        "target_token": solana_auto.target_token,
        "active_positions": len(solana_auto.active_positions),
        "positions": solana_auto.active_positions,
    }


# ==========================================
# SYSTEM LOGS
# ==========================================

@app.get("/api/system/logs")
async def system_logs():
    """Get recent system logs."""
    return {"logs": sys_logger.get_logs()}


# ==========================================
# TOKOCRYPTO PRICE
# ==========================================

@app.get("/api/toko/price/{symbol:path}")
async def toko_price(symbol: str):
    """Get current price from Tokocrypto."""
    try:
        ticker = await exchange.fetch_ticker(symbol)
        return {
            "symbol": symbol,
            "price": ticker["last"],
            "bid": ticker.get("bid"),
            "ask": ticker.get("ask"),
            "volume": ticker.get("baseVolume"),
        }
    except Exception as e:
        return {"error": str(e)}


# ==========================================
# ANALYTICS ENDPOINTS
# ==========================================

@app.get("/api/analytics/summary")
async def analytics_summary():
    """Get trading analytics summary."""
    return analytics.get_analytics_summary()


@app.get("/api/analytics/performance")
async def analytics_performance():
    """Get performance metrics."""
    return analytics.get_performance_metrics()


@app.get("/api/analytics/daily")
async def analytics_daily():
    """Get daily P&L breakdown."""
    return analytics.get_daily_pnl()


# ==========================================
# BOT MANAGER & UNIFIED POSITIONS (P5)
# ==========================================

from bot_manager import bot_registry, position_tracker, rotate_logs, archive_old_trades


@app.get("/api/bots")
async def list_bots():
    """Get status of all registered bots."""
    return {
        "bots": bot_registry.get_status(),
        "running": bot_registry.get_running_bots(),
    }


@app.post("/api/bots/{name}/start")
async def start_bot(name: str, background_tasks: BackgroundTasks):
    """Start a specific bot."""
    bot = bot_registry.get(name)
    if not bot:
        return {"error": f"Bot '{name}' not found"}
    
    if bot.is_running:
        return {"error": f"Bot '{name}' is already running"}
    
    background_tasks.add_task(bot.start)
    return {"status": "starting", "bot": name}


@app.post("/api/bots/{name}/stop")
async def stop_bot(name: str):
    """Stop a specific bot."""
    bot = bot_registry.get(name)
    if not bot:
        return {"error": f"Bot '{name}' not found"}
    
    bot.stop()
    return {"status": "stopped", "bot": name}


class BotConfigUpdate(BaseModel):
    config: dict


@app.post("/api/bots/{name}/config")
async def update_bot_config(name: str, update: BotConfigUpdate):
    """Hot-reload bot configuration without restart."""
    bot = bot_registry.get(name)
    if not bot:
        return {"error": f"Bot '{name}' not found"}
    
    bot_registry.update_bot_config(name, update.config)
    return {"status": "updated", "bot": name, "config": update.config}


@app.get("/api/positions")
async def unified_positions():
    """Get all positions across all bots."""
    return position_tracker.get_summary()


@app.get("/api/positions/{bot_type}")
async def positions_by_bot(bot_type: str):
    """Get positions for a specific bot type."""
    positions = position_tracker.get_by_bot_type(bot_type.upper())
    return {
        "bot_type": bot_type.upper(),
        "count": len(positions),
        "positions": [p.to_dict() for p in positions],
    }


@app.post("/api/maintenance/logs")
async def run_log_rotation():
    """Manually trigger log rotation."""
    rotate_logs(max_entries=500)
    return {"status": "success", "message": "Logs rotated"}


@app.post("/api/maintenance/archive")
async def run_archive():
    """Manually trigger trade archiving."""
    count = archive_old_trades(days_old=30)
    return {"status": "success", "archived_trades": count}


@app.get("/api/strategy/quality")
async def strategy_quality():
    """Get signal quality statistics for all strategies."""
    return strategy.get_signal_quality_stats()
