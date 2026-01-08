# File: backend/backtesting.py
"""
BACKTESTING ENGINE
Testing strategi trading menggunakan data historis tanpa risiko uang asli.
"""

import ccxt.async_support as ccxt
import pandas as pd
import asyncio
from datetime import datetime, timedelta
import strategy
from typing import Dict, List
import json

class BacktestEngine:
    def __init__(self, exchange_id='tokocrypto', initial_capital=1000.0):
        """
        Args:
            exchange_id: ID exchange untuk ambil data (default: tokocrypto)
            initial_capital: Modal awal dalam USDT untuk testing
        """
        self.exchange_id = exchange_id
        self.initial_capital = initial_capital
        self.trading_fee = 0.001  # 0.1% default (adjust sesuai exchange)
        self.slippage_pct = 0.0005  # 0.05% slippage estimation
        
    async def fetch_historical_data(self, symbol, timeframe='1h', days_back=30):
        """
        Mengambil data historis dari exchange
        
        Args:
            symbol: Trading pair (e.g., 'BTC/USDT')
            timeframe: Timeframe candle ('1m', '5m', '15m', '1h', '4h', '1d')
            days_back: Berapa hari ke belakang
            
        Returns:
            DataFrame dengan OHLCV data
        """
        exchange = getattr(ccxt, self.exchange_id)({
            'enableRateLimit': True,
        })
        
        try:
            await exchange.load_markets()
            
            # Calculate how many candles needed
            timeframe_minutes = {
                '1m': 1, '5m': 5, '15m': 15, '30m': 30,
                '1h': 60, '4h': 240, '1d': 1440
            }
            minutes = timeframe_minutes.get(timeframe, 60)
            limit = int((days_back * 24 * 60) / minutes)
            limit = min(limit, 1000)  # Max 1000 candles per request
            
            print(f"📊 Fetching {limit} candles of {symbol} ({timeframe})...")
            ohlcv = await exchange.fetch_ohlcv(symbol, timeframe=timeframe, limit=limit)
            
            df = pd.DataFrame(ohlcv, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            
            print(f"✅ Downloaded {len(df)} candles from {df['timestamp'].min()} to {df['timestamp'].max()}")
            
            await exchange.close()
            return df
            
        except Exception as e:
            print(f"❌ Error fetching data: {e}")
            await exchange.close()
            return None
    
    async def run_backtest(self, symbol, timeframe='1h', days_back=30, 
                          take_profit_pct=1.5, stop_loss_pct=3.0):
        """
        Menjalankan backtest dengan strategi yang ada
        
        Args:
            symbol: Trading pair
            timeframe: Timeframe untuk analisis
            days_back: Periode testing
            take_profit_pct: Take profit dalam % (default 1.5%)
            stop_loss_pct: Stop loss dalam % (default 3.0%)
            
        Returns:
            Dictionary berisi hasil backtest
        """
        print(f"\n{'='*60}")
        print(f"🔬 BACKTESTING: {symbol}")
        print(f"📅 Period: Last {days_back} days | Timeframe: {timeframe}")
        print(f"💰 Initial Capital: ${self.initial_capital}")
        print(f"📊 TP: {take_profit_pct}% | SL: {stop_loss_pct}%")
        print(f"{'='*60}\n")
        
        # Fetch historical data
        df = await self.fetch_historical_data(symbol, timeframe, days_back)
        if df is None or len(df) < 100:
            return {"error": "Insufficient data"}
        
        # Calculate indicators once for all data
        df['RSI'] = strategy.calculate_rsi(df['close'])
        df['MACD'], df['Signal_Line'], _ = strategy.calculate_macd(df['close'])
        df['Upper_BB'], df['Lower_BB'] = strategy.calculate_bollinger_bands(df['close'])
        
        # Backtest variables
        capital = self.initial_capital
        position = None  # {'entry_price': float, 'amount': float, 'entry_time': timestamp}
        trades = []
        
        # Iterate through each candle
        for i in range(100, len(df)):  # Start from 100 to have enough data for indicators
            current_row = df.iloc[:i+1]
            current_price = current_row['close'].iloc[-1]
            current_time = current_row['timestamp'].iloc[-1]
            
            # If we have an open position, check exit conditions
            if position:
                entry_price = position['entry_price']
                pnl_pct = ((current_price - entry_price) / entry_price) * 100
                
                # Check Take Profit
                if pnl_pct >= take_profit_pct:
                    sell_price = current_price * (1 - self.slippage_pct)  # Account for slippage
                    profit_before_fee = (sell_price - entry_price) * position['amount']
                    fee = sell_price * position['amount'] * self.trading_fee
                    net_profit = profit_before_fee - fee
                    capital += (position['amount'] * sell_price) - fee
                    
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': current_time,
                        'entry_price': entry_price,
                        'exit_price': sell_price,
                        'amount': position['amount'],
                        'profit': net_profit,
                        'profit_pct': pnl_pct,
                        'exit_reason': 'TAKE_PROFIT',
                        'fees_paid': fee
                    })
                    position = None
                    continue
                
                # Check Stop Loss
                if pnl_pct <= -stop_loss_pct:
                    sell_price = current_price * (1 - self.slippage_pct)
                    profit_before_fee = (sell_price - entry_price) * position['amount']
                    fee = sell_price * position['amount'] * self.trading_fee
                    net_profit = profit_before_fee - fee
                    capital += (position['amount'] * sell_price) - fee
                    
                    trades.append({
                        'entry_time': position['entry_time'],
                        'exit_time': current_time,
                        'entry_price': entry_price,
                        'exit_price': sell_price,
                        'amount': position['amount'],
                        'profit': net_profit,
                        'profit_pct': pnl_pct,
                        'exit_reason': 'STOP_LOSS',
                        'fees_paid': fee
                    })
                    position = None
                    continue
            
            # If no position, check for entry signals
            else:
                # Get strategy signals
                vote_rsi = strategy.check_rsi_strategy(current_row)
                vote_macd = strategy.check_macd_strategy(current_row)
                vote_bb = strategy.check_bb_strategy(current_row)
                
                buy_score = sum([1 for v in [vote_rsi, vote_macd, vote_bb] if v == "BUY"])
                
                # Enter position if 2+ buy signals
                if buy_score >= 2:
                    buy_price = current_price * (1 + self.slippage_pct)  # Account for slippage
                    fee = capital * self.trading_fee
                    amount = (capital - fee) / buy_price
                    
                    position = {
                        'entry_price': buy_price,
                        'amount': amount,
                        'entry_time': current_time
                    }
                    capital = 0  # All capital in position
        
        # Close any remaining open position at last price
        if position:
            sell_price = df['close'].iloc[-1] * (1 - self.slippage_pct)
            profit_before_fee = (sell_price - position['entry_price']) * position['amount']
            fee = sell_price * position['amount'] * self.trading_fee
            net_profit = profit_before_fee - fee
            capital += (position['amount'] * sell_price) - fee
            
            pnl_pct = ((sell_price - position['entry_price']) / position['entry_price']) * 100
            
            trades.append({
                'entry_time': position['entry_time'],
                'exit_time': df['timestamp'].iloc[-1],
                'entry_price': position['entry_price'],
                'exit_price': sell_price,
                'amount': position['amount'],
                'profit': net_profit,
                'profit_pct': pnl_pct,
                'exit_reason': 'END_OF_BACKTEST',
                'fees_paid': fee
            })
            position = None
        
        # Calculate statistics
        total_trades = len(trades)
        winning_trades = [t for t in trades if t['profit'] > 0]
        losing_trades = [t for t in trades if t['profit'] <= 0]
        
        win_rate = (len(winning_trades) / total_trades * 100) if total_trades > 0 else 0
        total_profit = sum([t['profit'] for t in trades])
        total_fees = sum([t['fees_paid'] for t in trades])
        
        final_capital = capital
        roi = ((final_capital - self.initial_capital) / self.initial_capital) * 100
        
        avg_win = sum([t['profit'] for t in winning_trades]) / len(winning_trades) if winning_trades else 0
        avg_loss = sum([t['profit'] for t in losing_trades]) / len(losing_trades) if losing_trades else 0
        profit_factor = abs(sum([t['profit'] for t in winning_trades]) / sum([t['profit'] for t in losing_trades])) if losing_trades and sum([t['profit'] for t in losing_trades]) != 0 else 0
        
        # Max Drawdown calculation
        equity_curve = [self.initial_capital]
        running_capital = self.initial_capital
        for trade in trades:
            running_capital += trade['profit']
            equity_curve.append(running_capital)
        
        peak = equity_curve[0]
        max_dd = 0
        for equity in equity_curve:
            if equity > peak:
                peak = equity
            dd = ((peak - equity) / peak) * 100
            if dd > max_dd:
                max_dd = dd
        
        results = {
            'status': 'completed',
            'symbol': symbol,
            'timeframe': timeframe,
            'period_days': days_back,
            'initial_capital': self.initial_capital,
            'final_capital': round(final_capital, 2),
            'net_profit': round(total_profit, 2),
            'roi_pct': round(roi, 2),
            'total_trades': total_trades,
            'winning_trades': len(winning_trades),
            'losing_trades': len(losing_trades),
            'win_rate_pct': round(win_rate, 2),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'profit_factor': round(profit_factor, 2),
            'total_fees_paid': round(total_fees, 2),
            'max_drawdown_pct': round(max_dd, 2),
            'trades': trades
        }
        
        # Print summary
        print(f"\n{'='*60}")
        print(f"📊 BACKTEST RESULTS")
        print(f"{'='*60}")
        print(f"💰 Initial Capital: ${self.initial_capital:.2f}")
        print(f"💵 Final Capital: ${final_capital:.2f}")
        print(f"📈 Net Profit: ${total_profit:.2f} ({roi:.2f}%)")
        print(f"📊 Total Trades: {total_trades}")
        print(f"✅ Win Rate: {win_rate:.2f}% ({len(winning_trades)}W / {len(losing_trades)}L)")
        print(f"💸 Total Fees: ${total_fees:.2f}")
        print(f"📉 Max Drawdown: {max_dd:.2f}%")
        print(f"⚖️ Profit Factor: {profit_factor:.2f}")
        print(f"{'='*60}\n")
        
        return results

# Helper function untuk batch backtest multiple symbols
async def batch_backtest(symbols: List[str], timeframe='1h', days_back=30):
    """
    Run backtest untuk multiple symbols sekaligus
    """
    engine = BacktestEngine()
    results = []
    
    for symbol in symbols:
        result = await engine.run_backtest(symbol, timeframe, days_back)
        results.append(result)
        await asyncio.sleep(1)  # Rate limiting
    
    # Sort by ROI
    results.sort(key=lambda x: x.get('roi_pct', -999), reverse=True)
    
    print(f"\n{'='*60}")
    print(f"📊 BATCH BACKTEST SUMMARY")
    print(f"{'='*60}")
    for r in results:
        if 'error' not in r:
            print(f"{r['symbol']:15} | ROI: {r['roi_pct']:+7.2f}% | Trades: {r['total_trades']:3} | Win Rate: {r['win_rate_pct']:5.1f}%")
    print(f"{'='*60}\n")
    
    return results

if __name__ == "__main__":
    # Example usage
    async def main():
        engine = BacktestEngine(initial_capital=1000.0)
        result = await engine.run_backtest('BTC/USDT', timeframe='1h', days_back=30)
        
        # Save to file
        with open('backtest_result.json', 'w') as f:
            json.dump(result, f, indent=2, default=str)
        print("💾 Results saved to backtest_result.json")
    
    asyncio.run(main())
