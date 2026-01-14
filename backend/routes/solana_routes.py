# File: backend/routes/solana_routes.py
"""
Solana/Jupiter trading endpoints
"""

from fastapi import APIRouter, BackgroundTasks, Depends, Request
from pydantic import BaseModel
import solana_tracker
from auth import require_trader, optional_auth, AuthUser
from rate_limiter import limiter, RATE_LIMIT_TRADING, RATE_LIMIT_READONLY
from jupiter_handler import jupiter_bot
from fastapi.responses import JSONResponse

router = APIRouter(prefix="/api/solana", tags=["solana"])


class QuoteRequest(BaseModel):
    input_token: str = "SOL"
    output_token: str
    amount: float
    slippage_bps: int = 100


class SwapRequest(BaseModel):
    quote_response: dict


@router.get("/balance")
@limiter.limit(RATE_LIMIT_READONLY)
async def sol_balance(request: Request, user: AuthUser = Depends(optional_auth)):
    """Get Solana token balances. Read-only access."""
    balances = await jupiter_bot.get_token_balances()
    return JSONResponse(content=balances)


@router.get("/history")
def sol_history(user: AuthUser = Depends(optional_auth)):
    """Get Solana trade history. Read-only access."""
    return JSONResponse(content=solana_tracker.load_history())


@router.post("/quote")
async def solana_quote(req: QuoteRequest, user: AuthUser = Depends(optional_auth)):
    """Get Jupiter swap quote. Read-only access."""
    quote = await jupiter_bot.get_quote(
        req.input_token, req.output_token, req.amount, req.slippage_bps
    )
    return JSONResponse(content=quote)


@router.post("/swap")
@limiter.limit(RATE_LIMIT_TRADING)
async def solana_swap(request: Request, req: SwapRequest, user: AuthUser = Depends(require_trader)):
    """Execute Jupiter swap. Requires trader role. Rate limited to 10/min."""
    result = await jupiter_bot.execute_swap(req.quote_response)
    return JSONResponse(content=result)


@router.post("/auto/toggle")
async def solana_auto_toggle(background_tasks: BackgroundTasks, user: AuthUser = Depends(require_trader)):
    """Toggle Solana auto trading bot. Requires trader role."""
    from solana_auto import solana_auto
    
    if solana_auto.is_running:
        solana_auto.stop()
        return JSONResponse(content={"status": "stopped", "toggled_by": user.user_id})
    else:
        background_tasks.add_task(solana_auto.start, "AUTO_HUNT")
        return JSONResponse(content={"status": "started", "toggled_by": user.user_id})


@router.get("/auto/status")
async def solana_auto_status(user: AuthUser = Depends(optional_auth)):
    """Get Solana auto bot status. Read-only access."""
    from solana_auto import solana_auto
    
    return JSONResponse(content={
        "is_running": solana_auto.is_running,
        "mode": solana_auto.mode,
        "target_token": solana_auto.target_token,
        "active_positions": len(solana_auto.active_positions),
        "positions": solana_auto.active_positions,
    })