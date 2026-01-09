import asyncio
import json
import os
import time
from datetime import datetime

import aiohttp
import pandas as pd
import pandas_ta as ta

from jupiter_handler import jupiter_bot, TOKENS
import solana_tracker
from solana_scanner import scanner
from solana_safety import safety_checker
import sys_logger 
import strategy

POSITIONS_FILE = "solana_positions.json"
TAKE_PROFIT_PCT = 50.0   # Target Profit (Bisa disesuaikan)
STOP_LOSS_PCT = -15.0    # Toleransi rugi (Stop Loss)
TRADE_AMOUNT_SOL = 0.001 
MAX_POSITIONS = 10        # 🔥 UPGRADE: Bot bisa pegang 3 koin sekaligus

class SolanaAutoBot:
    def __init__(self):
        self.is_running = False
        self.mode = "MANUAL_TARGET"
        self.target_token = "USDC"
        self.target_address = None
        self.target_pair_address = None
        
        # UBAH STRUKTUR DATA: Dari Single Object ke List (Array)
        self.active_positions = [] 
        self.recently_sold = [] 
        self.load_positions()

    def load_positions(self):
        if os.path.exists(POSITIONS_FILE):
            try:
                with open(POSITIONS_FILE, 'r') as f:
                    data = json.load(f)
                    # Migrasi otomatis dari format lama (dict) ke baru (list)
                    if isinstance(data, dict):
                        self.active_positions = [data]
                    elif isinstance(data, list):
                        self.active_positions = data
                    else:
                        self.active_positions = []
                        
                    if self.active_positions:
                        sys_logger.add_log(f"📂 Loaded {len(self.active_positions)} active positions")
            except Exception as e:
                sys_logger.add_log(f"⚠️ Load Error: {e}")
                self.active_positions = []

    def save_positions(self):
        with open(POSITIONS_FILE, 'w') as f:
            json.dump(self.active_positions, f, indent=4)

    def add_position(self, pos):
        self.active_positions.append(pos)
        self.save_positions()

    def remove_position(self, token_symbol):
        # Hapus token dari list posisi
        self.active_positions = [p for p in self.active_positions if p['token'] != token_symbol]
        self.save_positions()

    # --- API HELPER (GeckoTerminal - Gratis & Stabil) ---
    async def _fetch_candles(self, pair_address: str, interval="1m", limit=100):
        if not pair_address: return None
        url = f"https://api.geckoterminal.com/api/v2/networks/solana/pools/{pair_address}/ohlcv/minute?limit={limit}"
        
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200: return None
                    data = await resp.json()
            
            ohlcv_list = data.get("data", {}).get("attributes", {}).get("ohlcv_list", [])
            if not ohlcv_list: return None
                
            df = pd.DataFrame(ohlcv_list, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            return df
        except: return None

    def _technical_buy_signal(self, df):
        try:
            if len(df) < 20: return False, f"Not enough data: {len(df)}"
            df = df.copy()
            
            # Hitung Indikator
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            
            # Mapping Kolom (Aman jika nama kolom berubah)
            cols = df.columns
            rsi_col = next((c for c in cols if c.startswith('RSI')), None)
            macd_col = next((c for c in cols if c.startswith('MACD_') and not c.startswith('MACDs')), None)
            sig_col = next((c for c in cols if c.startswith('MACDs_')), None)
            low_bb = next((c for c in cols if c.startswith('BBL_')), None)
            
            if not all([rsi_col, macd_col, sig_col, low_bb]):
                return False, "Indicator calculation failed"

            last = df.iloc[-1]
            votes = []
            
            # 1. RSI Oversold (Diskon)
            if last[rsi_col] < 40: votes.append("RSI") 
            # 2. MACD Bullish Crossover (Momentum Naik)
            if last[macd_col] > last[sig_col]: votes.append("MACD")
            # 3. Harga dekat Lower BB (Buy on dip)
            if last['close'] <= last[low_bb] * 1.05: votes.append("BB")
            
            if len(votes) >= 2: return True, f"Strong: {', '.join(votes)}"
            return False, f"Weak ({len(votes)}/3)"
        except Exception as e: return False, str(e)

    # --- LOGIKA UTAMA (MULTI-TASKING) ---
    async def start(self, mode="MANUAL_TARGET", token_symbol=None):
        if self.is_running: return
        self.is_running = True
        self.mode = mode
        sys_logger.add_log(f"🚀 AUTO STARTED: {mode} (Max {MAX_POSITIONS} slots)")
        
        while self.is_running:
            try:
                await self.logic_loop()
            except Exception as e:
                sys_logger.add_log(f"⚠️ Loop Error: {e}")
            await asyncio.sleep(5) # Jeda agar CPU aman

    def stop(self):
        self.is_running = False
        sys_logger.add_log("🛑 AUTO STOPPED")

    async def logic_loop(self):
        # TUGAS 1: MONITORING (Cek semua koin yang dipegang)
        if self.active_positions:
            await self.check_all_exit_conditions()

        # TUGAS 2: SCANNING (Cari koin baru jika slot masih ada)
        current_count = len(self.active_positions)
        if current_count < MAX_POSITIONS:
            if self.mode == "AUTO_DISCOVERY":
                # Masukkan token yang sedang dipegang ke ignore list agar tidak dibeli lagi
                held_tokens = [p['token'] for p in self.active_positions]
                # Ignore list = token yang baru dijual + token yang sedang dipegang
                full_ignore_list = self.recently_sold + held_tokens
                
                gem = await scanner.find_gem(ignore_list=full_ignore_list)
                
                if gem:
                    self.target_token = gem['symbol']
                    self.target_address = gem['address']
                    self.target_pair_address = gem['pair_address']
                    TOKENS[self.target_token] = self.target_address 
                    sys_logger.add_log(f"🎯 Target Found: {self.target_token}")
                    await self.do_buy()
                else:
                    await asyncio.sleep(2)
            
            elif self.mode == "MANUAL_TARGET" and current_count == 0:
                # Mode manual hanya beli 1 kali
                await self.do_buy()
                self.stop() 

    async def do_buy(self):
        sys_logger.add_log(f"⚔️ Analyzing {self.target_token}...")

        # Helper untuk rotasi ignore list
        def add_to_ignore(token):
            self.recently_sold.append(token)
            if len(self.recently_sold) > 10: self.recently_sold.pop(0)

        # 1. Safety Check
        is_safe, reason, _ = await safety_checker.check_token(self.target_address)
        if not is_safe:
            sys_logger.add_log(f"🛑 Unsafe: {reason}")
            if self.mode == "AUTO_DISCOVERY": add_to_ignore(self.target_token)
            return

        # 2. Technical Check
        candles = await self._fetch_candles(self.target_pair_address)
        if candles is None or len(candles) < 30:
            sys_logger.add_log("⚠️ Not enough candles (<30m)")
            if self.mode == "AUTO_DISCOVERY": add_to_ignore(self.target_token)
            return
            
        is_buy, tech_reason = self._technical_buy_signal(candles)
        if not is_buy:
            sys_logger.add_log(f"⏸️ Technical Skip: {tech_reason}")
            # FIX: Jika teknikal jelek, masukkan ke ignore list agar scanner mencari yang lain
            if self.mode == "AUTO_DISCOVERY": 
                add_to_ignore(self.target_token) 
            return

        # 3. Execution (Beli)
        sys_logger.add_log(f"🛒 Executing Buy: {self.target_token}")
        quote = await jupiter_bot.get_quote("SOL", self.target_token, TRADE_AMOUNT_SOL)
        
        if "error" in quote:
            sys_logger.add_log(f"❌ Quote Error: {quote['error']}")
            if self.mode == "AUTO_DISCOVERY": add_to_ignore(self.target_token)
            return
        
        result = await jupiter_bot.execute_swap(quote['raw_data'])
        
        if result.get("status") == "success":
            output_amount = float(quote['output_estimate'].replace(",", ""))
            pos = {
                "token": self.target_token,
                "address": self.target_address,
                "entry_price_sol": TRADE_AMOUNT_SOL,
                "token_amount": output_amount,
                "txid": result['txid'],
                "timestamp": time.time()
            }
            self.add_position(pos)
            solana_tracker.save_trade(result['txid'], "SOL", self.target_token, TRADE_AMOUNT_SOL, output_amount)
            sys_logger.add_log(f"✅ BOUGHT {self.target_token}! Holding {len(self.active_positions)}/{MAX_POSITIONS}.")
        else:
            sys_logger.add_log("❌ Swap Failed")

    async def check_all_exit_conditions(self):
        # Cek setiap posisi satu per satu
        for pos in self.active_positions[:]: 
            await self.check_single_exit(pos)

    async def check_single_exit(self, pos):
        token = pos['token']
        amount = pos['token_amount']
        
        # Cek Harga
        quote = await jupiter_bot.get_quote(token, "SOL", 1)
        if "error" in quote: return 
        price_per_token = float(quote['output_estimate'].replace(",", ""))
        
        # Cegah Glitch -100% jika likuiditas belum terbaca
        if price_per_token <= 0: return 
        
        current_value_sol = price_per_token * amount
        initial_capital = pos['entry_price_sol']
        pnl_pct = ((current_value_sol - initial_capital) / initial_capital) * 100
        
        should_sell = False
        reason = ""
        
        if pnl_pct >= TAKE_PROFIT_PCT:
            should_sell = True
            reason = f"✅ TP Hit (+{pnl_pct:.2f}%)"
        elif pnl_pct <= STOP_LOSS_PCT:
            should_sell = True
            reason = f"❌ SL Hit ({pnl_pct:.2f}%)"
        
        if should_sell:
            sys_logger.add_log(f"🚨 Selling {token}: {reason}")
            
            full_quote = await jupiter_bot.get_quote(token, "SOL", amount)
            if "error" in full_quote: 
                sys_logger.add_log(f"❌ Sell Quote Error: {full_quote['error']}")
                return

            res = await jupiter_bot.execute_swap(full_quote['raw_data'])
            
            if res.get("status") == "success":
                sys_logger.add_log(f"✅ SOLD {token}!")
                solana_tracker.save_trade("SELL", token, "SOL", amount, current_value_sol, status=reason)
                self.remove_position(token)
                
                # Masukkan ke ignore list agar tidak terbeli lagi segera
                self.recently_sold.append(token)
                if len(self.recently_sold) > 10: self.recently_sold.pop(0)
            else:
                sys_logger.add_log(f"❌ Sell Fail: {res.get('message')}")

solana_auto = SolanaAutoBot()