# File: backend/routes/bot_routes.py
"""
Bot control and trade history endpoints
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
from auth import require_trader, optional_auth, AuthUser
from rate_limiter import limiter, RATE_LIMIT_TRADING, RATE_LIMIT_READONLY

router = APIRouter(prefix="/api", tags=["bot"])

# These will be injected from main.py
_state = {}


def init_state(state: dict):
    """Initialize module state from main.py"""
    global _state
    _state = state


@router.get("/")
def home():
    return {"status": "ready"}


@router.post("/bot/toggle")
@limiter.limit(RATE_LIMIT_TRADING)
async def toggle_bot(request: Request, bg: BackgroundTasks, user: AuthUser = Depends(require_trader)):
    """Toggle the Hunter trading bot on/off. Requires trader role. Rate limited to 10/min."""
    from main import IS_BOT_RUNNING, auto_trading_loop, CURRENT_SCAN_TARGET
    from websocket_manager import ws_manager
    import main
    import asyncio
    
    main.IS_BOT_RUNNING = not main.IS_BOT_RUNNING

    if main.IS_BOT_RUNNING:
        bg.add_task(auto_trading_loop)
        # Broadcast status change via WebSocket
        asyncio.create_task(ws_manager.broadcast_bot_status(True, main.CURRENT_SCAN_TARGET))
        return {"status": "running", "toggled_by": user.user_id}
    
    # Broadcast status change via WebSocket
    asyncio.create_task(ws_manager.broadcast_bot_status(False, "Stopped"))
    return {"status": "stopped", "toggled_by": user.user_id}


@router.get("/bot/status")
@limiter.limit(RATE_LIMIT_READONLY)
def bot_status(request: Request):
    """Get current bot status."""
    from main import IS_BOT_RUNNING, CURRENT_SCAN_TARGET
    return {
        "is_running": IS_BOT_RUNNING,
        "current_activity": CURRENT_SCAN_TARGET,
        "running": IS_BOT_RUNNING,  # Legacy
        "activity": CURRENT_SCAN_TARGET,  # Legacy
    }


@router.get("/bot/mode")
async def bot_mode():
    """Get current bot mode (LIVE/PAPER/BACKTEST)."""
    from main import BOT_MODE
    return {"mode": BOT_MODE}


@router.get("/trade/history")
def trade_history():
    """Get recent trade history."""
    from database_pg import get_db_session, Trade
    
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
                'source': 'Hunter',
            }
            for t in trades
        ]
    finally:
        session.close()


@router.get("/trade/ledger")
def trade_ledger(trade_id: int = None, bot_type: str = None, limit: int = 100):
    """Get immutable trade ledger entries."""
    from database_pg import get_db_session, TradeLedger
    
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


@router.get("/trade/ledger/{trade_id}")
def trade_ledger_by_id(trade_id: int):
    """Get all ledger entries for a specific trade."""
    from database_pg import get_db_session, TradeLedger
    
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


@router.get("/toko/price/{symbol:path}")
async def toko_price(symbol: str):
    """Get current price from Tokocrypto/Binance."""
    from main import exchange
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
