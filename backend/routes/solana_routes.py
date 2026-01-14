# File: backend/routes/solana_routes.py
"""
Solana/Jupiter trading endpoints
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import solana_tracker

router = APIRouter(prefix="/api/solana", tags=["solana"])


class QuoteRequest(BaseModel):
    input_token: str = "SOL"
    output_token: str
    amount: float
    slippage_bps: int = 100


class SwapRequest(BaseModel):
    quote_response: dict


@router.get("/balance")
async def sol_balance():
    """Get Solana token balances."""
    from jupiter_handler import jupiter_bot
    return await jupiter_bot.get_token_balances()


@router.get("/history")
def sol_history():
    """Get Solana trade history."""
    return solana_tracker.load_history()


@router.post("/quote")
async def solana_quote(req: QuoteRequest):
    """Get Jupiter swap quote."""
    from jupiter_handler import jupiter_bot
    quote = await jupiter_bot.get_quote(
        req.input_token, req.output_token, req.amount, req.slippage_bps
    )
    return quote


@router.post("/swap")
async def solana_swap(req: SwapRequest):
    """Execute Jupiter swap."""
    from jupiter_handler import jupiter_bot
    result = await jupiter_bot.execute_swap(req.quote_response)
    return result


@router.post("/auto/toggle")
async def solana_auto_toggle(background_tasks: BackgroundTasks):
    """Toggle Solana auto trading bot."""
    from solana_auto import solana_auto
    
    if solana_auto.is_running:
        solana_auto.stop()
        return {"status": "stopped"}
    else:
        background_tasks.add_task(solana_auto.start, "AUTO_HUNT")
        return {"status": "started"}


@router.get("/auto/status")
async def solana_auto_status():
    """Get Solana auto bot status."""
    from solana_auto import solana_auto
    
    return {
        "is_running": solana_auto.is_running,
        "mode": solana_auto.mode,
        "target_token": solana_auto.target_token,
        "active_positions": len(solana_auto.active_positions),
        "positions": solana_auto.active_positions,
    }
