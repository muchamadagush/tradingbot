# File: backend/routes/system_routes.py
"""
System, maintenance, and bot manager endpoints
"""

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel
import sys_logger
import strategy

router = APIRouter(prefix="/api", tags=["system"])


class BotConfigUpdate(BaseModel):
    config: dict


@router.get("/system/logs")
async def system_logs():
    """Get recent system logs."""
    return {"logs": sys_logger.get_logs()}


@router.get("/bots")
async def list_bots():
    """Get status of all registered bots."""
    from bot_manager import bot_registry
    return {
        "bots": bot_registry.get_status(),
        "running": bot_registry.get_running_bots(),
    }


@router.post("/bots/{name}/start")
async def start_bot(name: str, background_tasks: BackgroundTasks):
    """Start a specific bot."""
    from bot_manager import bot_registry
    
    bot = bot_registry.get(name)
    if not bot:
        return {"error": f"Bot '{name}' not found"}
    
    if bot.is_running:
        return {"error": f"Bot '{name}' is already running"}
    
    background_tasks.add_task(bot.start)
    return {"status": "starting", "bot": name}


@router.post("/bots/{name}/stop")
async def stop_bot(name: str):
    """Stop a specific bot."""
    from bot_manager import bot_registry
    
    bot = bot_registry.get(name)
    if not bot:
        return {"error": f"Bot '{name}' not found"}
    
    bot.stop()
    return {"status": "stopped", "bot": name}


@router.post("/bots/{name}/config")
async def update_bot_config(name: str, update: BotConfigUpdate):
    """Hot-reload bot configuration without restart."""
    from bot_manager import bot_registry
    
    bot = bot_registry.get(name)
    if not bot:
        return {"error": f"Bot '{name}' not found"}
    
    bot_registry.update_bot_config(name, update.config)
    return {"status": "updated", "bot": name, "config": update.config}


@router.get("/positions")
async def unified_positions():
    """Get all positions across all bots."""
    from bot_manager import position_tracker
    return position_tracker.get_summary()


@router.get("/positions/{bot_type}")
async def positions_by_bot(bot_type: str):
    """Get positions for a specific bot type."""
    from bot_manager import position_tracker
    
    positions = position_tracker.get_by_bot_type(bot_type.upper())
    return {
        "bot_type": bot_type.upper(),
        "count": len(positions),
        "positions": [p.to_dict() for p in positions],
    }


@router.post("/maintenance/logs")
async def run_log_rotation():
    """Manually trigger log rotation."""
    from bot_manager import rotate_logs
    rotate_logs(max_entries=500)
    return {"status": "success", "message": "Logs rotated"}


@router.post("/maintenance/archive")
async def run_archive():
    """Manually trigger trade archiving."""
    from bot_manager import archive_old_trades
    count = archive_old_trades(days_old=30)
    return {"status": "success", "archived_trades": count}


@router.get("/strategy/quality")
async def strategy_quality():
    """Get signal quality statistics for all strategies."""
    return strategy.get_signal_quality_stats()
