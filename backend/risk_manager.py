# File: backend/risk_manager.py
import os
from datetime import datetime, date
from typing import Dict, Optional, List, Union
from pydantic import BaseModel

# Menggunakan Pydantic agar kompatibel dengan main.py
class RiskLimits(BaseModel):
    max_position_size_pct: float = 20.0
    max_portfolio_drawdown_pct: float = 15.0
    max_daily_loss_pct: float = 5.0
    stop_loss_pct: float = 3.0
    max_open_positions: int = 5
    risk_per_trade_pct: float = 2.0

class RiskManager:
    # [FIX] Urutan parameter dikembalikan: initial_balance duluan, baru limits
    def __init__(self, initial_balance: float = 1000.0, limits: RiskLimits = None):
        self.initial_balance = float(initial_balance)
        self.limits = limits if limits else RiskLimits()
        
        self.current_balance = self.initial_balance
        self.daily_pnl = 0.0
        self.last_reset_date = date.today()
        self.peak_balance = self.initial_balance
        self.is_trading_allowed = True
        self.trades_today = 0

    def _check_reset_daily(self):
        """Reset PnL harian jika ganti hari"""
        if date.today() > self.last_reset_date:
            self.daily_pnl = 0.0
            self.trades_today = 0
            self.last_reset_date = date.today()
            # Reset izin trading (kecuali jika drawdown global masih kena)
            self.is_trading_allowed = True
            self.check_limits()

    def record_trade_pnl(self, pnl: float):
        """
        Dipanggil oleh main.py setelah SELL.
        Mencatat untung/rugi untuk menghitung Daily Loss Limit.
        """
        self._check_reset_daily()
        self.daily_pnl += pnl
        self.current_balance += pnl
        self.trades_today += 1
        
        # Update Peak Balance (High Water Mark) untuk perhitungan Drawdown
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
            
        # Cek apakah limit terlanggar setelah trade ini
        self.check_limits()

    def check_limits(self):
        """Internal function: Cek apakah batas kerugian terlanggar"""
        # 1. Cek Daily Loss Limit
        daily_loss_pct = 0
        if self.initial_balance > 0:
            # PnL negatif berarti rugi
            if self.daily_pnl < 0:
                daily_loss_pct = (abs(self.daily_pnl) / self.initial_balance) * 100
        
        if self.daily_pnl < 0 and daily_loss_pct >= self.limits.max_daily_loss_pct:
            self.is_trading_allowed = False
            return False, f"Daily loss limit hit (-{daily_loss_pct:.2f}%)"

        # 2. Cek Max Drawdown (Penurunan dari titik tertinggi)
        drawdown = 0
        if self.peak_balance > 0:
            drawdown = (self.peak_balance - self.current_balance) / self.peak_balance * 100
            
        if drawdown >= self.limits.max_portfolio_drawdown_pct:
            self.is_trading_allowed = False
            return False, f"Max drawdown hit ({drawdown:.2f}%)"
            
        self.is_trading_allowed = True
        return True, "OK"

    def can_trade_new(self):
        """
        [WAJIB ADA] Dipanggil oleh main.py sebelum scanning pasar.
        Mengembalikan True jika trading diizinkan (tidak kena limit harian).
        """
        self._check_reset_daily()
        is_ok, reason = self.check_limits()
        # Logging opsional bisa ditaruh di sini
        return is_ok

    def can_open_position(self, current_open_positions: int, wallet_balance: float, trade_amount: float):
        """
        [WAJIB ADA] Validasi spesifik sebelum membuka posisi baru.
        """
        # 1. Cek Global Switch (Daily Limit)
        if not self.can_trade_new():
            return {"approved": False, "reasons": ["Trading halted (Daily Limit/Drawdown)"]}
            
        reasons = []
        
        # 2. Cek Max Open Positions (Slot Penuh?)
        if current_open_positions >= self.limits.max_open_positions:
            reasons.append(f"Max positions reached ({current_open_positions}/{self.limits.max_open_positions})")

        # 3. Cek Saldo Cukup
        if trade_amount > wallet_balance:
            reasons.append(f"Insufficient balance (${wallet_balance:.2f} < ${trade_amount:.2f})")
            
        # 4. Cek Ukuran Posisi (Risk Sizing) - Optional Safety
        if wallet_balance > 0:
            pct_size = (trade_amount / wallet_balance) * 100
            if pct_size > self.limits.max_position_size_pct:
                 reasons.append(f"Position size too big ({pct_size:.1f}% > {self.limits.max_position_size_pct}%)")

        if reasons:
            return {"approved": False, "reasons": reasons}
            
        return {"approved": True, "reasons": []}

    def get_risk_summary(self, current_equity: float, open_positions: int):
        """Untuk API Dashboard Frontend"""
        self.current_balance = current_equity 
        self.check_limits()
        
        drawdown = 0
        if self.peak_balance > 0:
            drawdown = (self.peak_balance - self.current_balance) / self.peak_balance * 100
            
        return {
            "can_trade": self.is_trading_allowed,
            "daily_pnl": self.daily_pnl,
            "drawdown_pct": drawdown,
            "open_positions": open_positions,
            "limits": self.limits.dict() if hasattr(self.limits, 'dict') else self.limits.__dict__
        }

    def calculate_kelly_criterion(self, win_rate, avg_win, avg_loss):
        """Kalkulator Kelly untuk API Frontend"""
        if avg_loss == 0: return 0
        b = avg_win / avg_loss
        p = win_rate / 100
        q = 1 - p
        f = (b * p - q) / b
        return max(0, f * 100) # Return percentage