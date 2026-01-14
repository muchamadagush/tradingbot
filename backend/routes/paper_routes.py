# File: backend/routes/paper_routes.py
"""
Paper trading endpoints
"""

from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter(prefix="/api/paper", tags=["paper"])


class PaperBuyRequest(BaseModel):
    symbol: str
    amount_usdt: float


class PaperSellRequest(BaseModel):
    symbol: str
    percentage: float = 100


@router.get("/account")
async def paper_account():
    """Get paper trading account summary."""
    from main import exchange
    import paper_trading
    
    prices = {}
    for s in paper_trading.paper_account.positions:
        try:
            ticker = await exchange.fetch_ticker(s)
            prices[s] = ticker["last"]
        except:
            pass
    return paper_trading.paper_account.get_account_summary(prices)


@router.post("/buy")
async def paper_buy(req: PaperBuyRequest):
    """Execute paper buy order."""
    from main import exchange, hunter_risk
    import paper_trading
    
    try:
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


@router.post("/sell")
async def paper_sell(req: PaperSellRequest):
    """Execute paper sell order."""
    from main import exchange
    import paper_trading
    
    try:
        ticker = await exchange.fetch_ticker(req.symbol)
        price = ticker["last"]
    except Exception as e:
        return {"status": "failed", "reason": f"Failed to fetch price: {e}"}
    
    result = paper_trading.paper_account.place_market_sell(
        req.symbol, req.percentage, price
    )
    return result


@router.post("/reset")
async def paper_reset():
    """Reset paper trading account."""
    from main import PAPER_INITIAL_BALANCE
    import paper_trading
    
    paper_trading.paper_account.reset_account(PAPER_INITIAL_BALANCE)
    return {"status": "reset", "balance": PAPER_INITIAL_BALANCE}


@router.get("/orders")
async def paper_orders():
    """Get paper trading order history."""
    import paper_trading
    return paper_trading.paper_account.orders_history


@router.get("/trades")
async def paper_trades():
    """Get paper trading trade history."""
    import paper_trading
    return paper_trading.paper_account.trades_history
