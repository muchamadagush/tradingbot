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
# ROUTER IMPORTS AND MOUNTING
# ==========================================

from routes import (
    bot_router, paper_router, solana_router, risk_router,
    backtest_router, analytics_router, fee_router, system_router
)

# Mount all routers
app.include_router(bot_router)
app.include_router(paper_router)
app.include_router(solana_router)
app.include_router(risk_router)
app.include_router(backtest_router)
app.include_router(analytics_router)
app.include_router(fee_router)
app.include_router(system_router)
