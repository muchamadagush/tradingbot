# File: backend/analytics.py
"""
Analytics Module untuk menghitung profit/loss dari trades
Mendukung Solana dan Tokocrypto dengan filtering by date dan timeframe
"""

import json
import os
import time
import asyncio
import aiohttp
from datetime import datetime, timedelta
import pandas as pd
from typing import Dict, List, Tuple, Optional

# Import directly from PostgreSQL database layer
from database_pg import get_db_session, Trade, TradeState, get_all_solana_trades

# =========================================
# SOL PRICE CACHE
# =========================================
_sol_price_cache = {
    "price": 200.0,      # Default/last known price
    "timestamp": 0,       # Last fetch time
    "ttl": 60            # Cache TTL in seconds
}

# =========================================
# ANALYTICS SUMMARY API FUNCTIONS
# =========================================

def get_analytics_summary():
    """
    Returns a combined summary of Solana and Tokocrypto analytics.
    """
    sol_price = get_current_sol_price()
    solana = calculate_solana_analytics(sol_to_usd=sol_price)
    toko = calculate_tokocrypto_analytics()
    return {
        "solana": solana["summary"] if "summary" in solana else {},
        "tokocrypto": toko["summary"] if "summary" in toko else {}
    }

def get_performance_metrics():
    """
    Returns performance metrics for Solana and Tokocrypto (alias for summary).
    """
    return get_analytics_summary()

def get_daily_pnl():
    """
    Returns daily P&L breakdown for Solana and Tokocrypto.
    """
    sol_price = get_current_sol_price()
    solana = calculate_solana_analytics(timeframe="daily", sol_to_usd=sol_price)
    toko = calculate_tokocrypto_analytics(timeframe="daily")
    return {
        "solana": solana["data"] if "data" in solana else [],
        "tokocrypto": toko["data"] if "data" in toko else []
    }
# =========================================
# SOLANA ANALYTICS
# =========================================

def load_solana_trades():
    """Load solana trades from PostgreSQL"""
    return get_all_solana_trades()


def calculate_solana_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timeframe: str = "daily",
    sol_to_usd: float = 200.0  # Default SOL price, should be fetched from API
) -> Dict:
    """
    Calculate profit/loss analytics for Solana trades using CASHFLOW method.
    
    Logika Cashflow (semua dalam SOL):
    - BUY side: Keluar SOL (modal negatif). Profit = -amount_in (kerugian = keluar uang)
    - SELL side: Masuk SOL (revenue positif). Profit = +amount_out (keuntungan = masuk uang)
    
    Cumulative profit = total net cashflow dari semua transaksi
    
    Args:
        start_date: ISO format (YYYY-MM-DD) or None for all
        end_date: ISO format (YYYY-MM-DD) or None for today
        timeframe: 'daily', 'weekly', 'monthly', 'yearly'
        sol_to_usd: Current SOL price in USD
    
    Returns:
        {
            "data": [
                {"date": "2024-01-01", "profit_sol": 0.5, "profit_usd": 100, "cumulative_profit_sol": 0.5, "cumulative_profit_usd": 100},
                ...
            ],
            "summary": {
                "total_profit_sol": 5.0,
                "total_profit_usd": 1000.0,
                "total_loss_sol": -2.0,
                "total_loss_usd": -400.0,
                "net_profit_sol": 3.0,
                "net_profit_usd": 600.0,
                "total_trades": 20,
                "winning_trades": 15,
                "losing_trades": 5,
                "win_rate": 75.0
            }
        }
    """
    trades = load_solana_trades()
    if not trades:
        return {
            "data": [],
            "summary": {
                "total_profit_sol": 0.0,
                "total_profit_usd": 0.0,
                "total_loss_sol": 0.0,
                "total_loss_usd": 0.0,
                "net_profit_sol": 0.0,
                "net_profit_usd": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0
            }
        }
    
    # PERBAIKAN: Filter semua transaksi valid, tidak hanya "Success"
    # Termasuk status yang mengandung "Hit", "Loss", "Win", atau side "SELL"
    valid_trades = []
    for t in trades:
        status = str(t.get("status", "")).upper()
        side = str(t.get("side", "")).upper()
        
        # Ambil transaksi jika:
        # 1. Status "SUCCESS" (normal completion)
        # 2. Status mengandung "HIT" (Stop Loss atau Take Profit)
        # 3. Status mengandung "LOSS" atau "WIN" (Cut Loss atau Win)
        # 4. Side adalah "SELL" (exit transaksi)
        # 5. Memiliki valid amount_in dan amount_out
        
        if (status == "SUCCESS" or 
            "HIT" in status or 
            "LOSS" in status or 
            "WIN" in status or 
            side == "SELL"):
            
            # Validasi: harus punya amount_in dan amount_out
            if t.get("amount_in") is not None and t.get("amount_out") is not None:
                valid_trades.append(t)
    
    if not valid_trades:
        return {
            "data": [],
            "summary": {
                "total_profit_sol": 0.0,
                "total_profit_usd": 0.0,
                "total_loss_sol": 0.0,
                "total_loss_usd": 0.0,
                "net_profit_sol": 0.0,
                "net_profit_usd": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0
            }
        }
    
    # Convert to DataFrame for easier manipulation
    df = pd.DataFrame(valid_trades)
    df['timestamp'] = pd.to_datetime(df['timestamp'])
    
    # Filter by date range
    if start_date:
        start_dt = pd.to_datetime(start_date)
        df = df[df['timestamp'] >= start_dt]
    
    if end_date:
        end_dt = pd.to_datetime(end_date)
        df = df[df['timestamp'] <= end_dt]
    
    if df.empty:
        return {
            "data": [],
            "summary": {
                "total_profit_sol": 0.0,
                "total_profit_usd": 0.0,
                "total_loss_sol": 0.0,
                "total_loss_usd": 0.0,
                "net_profit_sol": 0.0,
                "net_profit_usd": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0
            }
        }
    
    # PERBAIKAN: Gunakan metode CASHFLOW murni dalam satuan SOL
    # BUY: profit = -amount_in (keluar SOL = kerugian/modal)
    # SELL: profit = +amount_out (masuk SOL = keuntungan/revenue)
    # JANGAN kurangkan Token dengan SOL!
    
    def calculate_profit_sol(row):
        side = str(row.get('side', '')).upper()
        amount_in = float(row.get('amount_in', 0))
        amount_out = float(row.get('amount_out', 0))
        
        if side == 'BUY':
            # BUY: Keluar SOL (modal). Profit = -amount_in (negatif)
            return -amount_in
        elif side == 'SELL':
            # SELL: Masuk SOL (revenue). Profit = +amount_out (positif)
            return amount_out
        else:
            # Default: return 0
            return 0.0
    
    df['profit_sol'] = df.apply(calculate_profit_sol, axis=1)
    df['profit_usd'] = df['profit_sol'] * sol_to_usd
    
    # Resample based on timeframe untuk grouping
    df_grouped = df.set_index('timestamp').resample(_get_pandas_freq(timeframe))
    
    result_data = []
    cumulative_profit_sol = 0.0
    cumulative_profit_usd = 0.0
    
    for date, group in df_grouped:
        if group.empty:
            continue
        
        period_profit_sol = group['profit_sol'].sum()
        period_profit_usd = group['profit_usd'].sum()
        cumulative_profit_sol += period_profit_sol
        cumulative_profit_usd += period_profit_usd
        
        result_data.append({
            "date": date.strftime("%Y-%m-%d") if timeframe == "daily" else date.strftime("%Y-W%U"),
            "profit_sol": round(period_profit_sol, 8),
            "profit_usd": round(period_profit_usd, 2),
            "cumulative_profit_sol": round(cumulative_profit_sol, 8),
            "cumulative_profit_usd": round(cumulative_profit_usd, 2)
        })
    
    # Calculate summary statistics
    # PERBAIKAN: Total Trades, Winning/Losing Trades hanya dari SELL side
    # Ini menghitung kesuksesan exit/penjualan, bukan entry/pembelian
    
    # Net profit: tetap gunakan semua transaksi (BUY + SELL) untuk arus kas real
    net_profit_sol = df['profit_sol'].sum()
    net_profit_usd = net_profit_sol * sol_to_usd
    
    # Total Profit & Loss: hitung dari semua transaksi yang cashflow positif/negatif
    total_profit_sol = df[df['profit_sol'] > 0]['profit_sol'].sum()
    total_loss_sol = df[df['profit_sol'] < 0]['profit_sol'].sum()
    total_profit_usd = total_profit_sol * sol_to_usd
    total_loss_usd = total_loss_sol * sol_to_usd
    
    # PERBAIKAN: Filter hanya SELL transaksi untuk metrics
    df_sell = df[df['side'].str.upper() == 'SELL']
    
    # Total Trades: hanya hitung SELL transaksi (exit trades)
    total_trades = len(df_sell)
    
    if total_trades > 0:
        # Winning Trades: SELL dengan status mengandung TP/Profit/Win/Success (tidak mengandung SL)
        winning_trades = 0
        for idx, row in df_sell.iterrows():
            status = str(row.get('status', '')).upper()
            has_winning_indicator = ('TP' in status or 'PROFIT' in status or 
                                     'WIN' in status or 'SUCCESS' in status)
            has_losing_indicator = ('SL' in status or 'LOSS' in status or 'CUT' in status)
            
            if has_winning_indicator and not has_losing_indicator:
                winning_trades += 1
        
        # Losing Trades: SELL dengan status mengandung SL/Loss/Cut
        losing_trades = 0
        for idx, row in df_sell.iterrows():
            status = str(row.get('status', '')).upper()
            has_losing_indicator = ('SL' in status or 'LOSS' in status or 'CUT' in status)
            
            if has_losing_indicator:
                losing_trades += 1
        
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    else:
        winning_trades = 0
        losing_trades = 0
        win_rate = 0.0
    
    return {
        "data": result_data,
        "summary": {
            "total_profit_sol": round(total_profit_sol, 8),
            "total_profit_usd": round(total_profit_usd, 2),
            "total_loss_sol": round(total_loss_sol, 8),
            "total_loss_usd": round(total_loss_usd, 2),
            "net_profit_sol": round(net_profit_sol, 8),
            "net_profit_usd": round(net_profit_usd, 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2)
        }
    }


# =========================================
# TOKOCRYPTO ANALYTICS
# =========================================

def calculate_tokocrypto_analytics(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    timeframe: str = "daily"
) -> Dict:
    """
    Calculate profit/loss analytics for Tokocrypto trades
    Query from SQLite database
    
    Args:
        start_date: ISO format (YYYY-MM-DD) or None for all
        end_date: ISO format (YYYY-MM-DD) or None for today
        timeframe: 'daily', 'weekly', 'monthly', 'yearly'
    
    Returns:
        {
            "data": [
                {"date": "2024-01-01", "profit_usdt": 100, "cumulative_profit": 100},
                ...
            ],
            "summary": {
                "total_profit_usdt": 500,
                "total_loss_usdt": -200,
                "net_profit_usdt": 300,
                "total_trades": 20,
                "winning_trades": 15,
                "losing_trades": 5,
                "win_rate": 75.0
            }
        }
    """
    session = get_db_session()
    try:
        # Get closed trades from PostgreSQL
        query = session.query(Trade).filter(Trade.status == TradeState.CLOSED)
        
        if start_date:
            start_dt = pd.to_datetime(start_date)
            query = query.filter(Trade.closed_at >= start_dt)
        
        if end_date:
            end_dt = pd.to_datetime(end_date)
            query = query.filter(Trade.closed_at <= end_dt)
        
        trades_obj = query.order_by(Trade.closed_at.asc()).all()
        
        # Convert to dict format for compatibility
        rows = [
            {
                'id': t.id,
                'symbol': t.symbol,
                'buy_price': t.buy_price,
                'sell_price': t.sell_price,
                'amount': t.amount,
                'profit_usdt': t.profit_usdt,
                'created_at': t.created_at,
                'closed_at': t.closed_at,
            }
            for t in trades_obj
        ]
    finally:
        session.close()
    
    if not rows:
        return {
            "data": [],
            "summary": {
                "total_profit_usdt": 0.0,
                "total_loss_usdt": 0.0,
                "net_profit_usdt": 0.0,
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
                "win_rate": 0.0
            }
        }
    
    # Convert to DataFrame
    df = pd.DataFrame([dict(row) for row in rows])
    df['closed_at'] = pd.to_datetime(df['closed_at'])
    
    # Resample based on timeframe
    df_grouped = df.set_index('closed_at').resample(_get_pandas_freq(timeframe))
    
    result_data = []
    cumulative_profit = 0.0
    
    for date, group in df_grouped:
        if group.empty:
            continue
        
        period_profit = group['profit_usdt'].sum()
        cumulative_profit += period_profit
        
        result_data.append({
            "date": date.strftime("%Y-%m-%d") if timeframe == "daily" else date.strftime("%Y-W%U"),
            "profit_usdt": round(period_profit, 2),
            "cumulative_profit": round(cumulative_profit, 2)
        })
    
    # Calculate summary statistics
    total_profit = df[df['profit_usdt'] > 0]['profit_usdt'].sum()
    total_loss = df[df['profit_usdt'] < 0]['profit_usdt'].sum()
    net_profit = total_profit + total_loss
    
    winning_trades = len(df[df['profit_usdt'] > 0])
    losing_trades = len(df[df['profit_usdt'] < 0])
    total_trades = len(df)
    win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
    
    return {
        "data": result_data,
        "summary": {
            "total_profit_usdt": round(total_profit, 2),
            "total_loss_usdt": round(total_loss, 2),
            "net_profit_usdt": round(net_profit, 2),
            "total_trades": total_trades,
            "winning_trades": winning_trades,
            "losing_trades": losing_trades,
            "win_rate": round(win_rate, 2)
        }
    }


# =========================================
# HELPER FUNCTIONS
# =========================================

def _get_pandas_freq(timeframe: str) -> str:
    """Convert timeframe to pandas frequency"""
    freq_map = {
        "daily": "D",
        "weekly": "W",
        "monthly": "M",
        "yearly": "Y"
    }
    return freq_map.get(timeframe, "D")


def get_current_sol_price() -> float:
    """
    Get current SOL price with caching.
    Uses sync wrapper for async fetch.
    Falls back to last known price if fetch fails.
    """
    global _sol_price_cache
    
    # Check cache validity
    now = time.time()
    if now - _sol_price_cache["timestamp"] < _sol_price_cache["ttl"]:
        return _sol_price_cache["price"]
    
    # Try to fetch new price
    try:
        # Check if we're in an async context
        try:
            loop = asyncio.get_running_loop()
            # We're in async context, can't use run_until_complete
            # Return cached value, let async version update it
            return _sol_price_cache["price"]
        except RuntimeError:
            # No running loop, safe to create one
            pass
        
        # Sync fetch using new event loop
        price = asyncio.run(_fetch_sol_price_async())
        if price > 0:
            _sol_price_cache["price"] = price
            _sol_price_cache["timestamp"] = now
            return price
    except Exception as e:
        print(f"⚠️ SOL price fetch error: {e}")
    
    # Return cached/default price
    return _sol_price_cache["price"]


async def get_current_sol_price_async() -> float:
    """
    Async version of SOL price fetcher.
    Use this in async contexts (e.g., FastAPI endpoints).
    """
    global _sol_price_cache
    
    # Check cache validity
    now = time.time()
    if now - _sol_price_cache["timestamp"] < _sol_price_cache["ttl"]:
        return _sol_price_cache["price"]
    
    # Fetch new price
    try:
        price = await _fetch_sol_price_async()
        if price > 0:
            _sol_price_cache["price"] = price
            _sol_price_cache["timestamp"] = now
            return price
    except Exception as e:
        print(f"⚠️ SOL price fetch error: {e}")
    
    return _sol_price_cache["price"]


async def _fetch_sol_price_async() -> float:
    """
    Fetch SOL price from Jupiter Price API.
    Returns 0 if fetch fails (caller should use cached value).
    """
    try:
        timeout = aiohttp.ClientTimeout(total=5)  # 5 second timeout
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(
                "https://price.jup.ag/v4/price?ids=SOL"
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    price = data.get("data", {}).get("SOL", {}).get("price", 0)
                    return float(price) if price else 0
    except asyncio.TimeoutError:
        print("⚠️ SOL price fetch timeout")
    except Exception as e:
        print(f"⚠️ SOL price fetch error: {e}")
    
    return 0
