# File: backend/routes/backtest_routes.py
"""
Backtesting endpoints
"""

from fastapi import APIRouter
from pydantic import BaseModel
import json

router = APIRouter(prefix="/api/backtest", tags=["backtest"])


class BacktestRequest(BaseModel):
    symbol: str
    strategy: str = "RSI_MACD"
    start_date: str = None
    end_date: str = None
    initial_capital: float = 1000
    timeframe: str = "1m"


class BatchBacktestRequest(BaseModel):
    symbols: list
    strategy: str = "RSI_MACD"
    initial_capital: float = 1000


@router.post("/run")
async def backtest_run(req: BacktestRequest):
    """Run a backtest."""
    import backtesting
    from database_pg import BacktestResult, session_scope
    
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


@router.post("/batch")
async def backtest_batch(req: BatchBacktestRequest):
    """Run batch backtest on multiple symbols."""
    import backtesting
    
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


@router.get("/history")
async def backtest_history():
    """Get backtest history."""
    from database_pg import BacktestResult, get_db_session
    
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
