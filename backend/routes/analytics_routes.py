# File: backend/routes/analytics_routes.py
"""
Analytics endpoints
"""

from fastapi import APIRouter
import analytics

router = APIRouter(prefix="/api/analytics", tags=["analytics"])


@router.get("/summary")
async def analytics_summary():
    """Get trading analytics summary."""
    return analytics.get_analytics_summary()


@router.get("/performance")
async def analytics_performance():
    """Get performance metrics."""
    return analytics.get_performance_metrics()


@router.get("/daily")
async def analytics_daily():
    """Get daily P&L breakdown."""
    return analytics.get_daily_pnl()
