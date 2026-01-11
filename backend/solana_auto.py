import asyncio
import json
import os
import time
from datetime import datetime

import aiohttp
import pandas as pd
import pandas_ta as ta
from solders.pubkey import Pubkey  # Import baru untuk cek desimal

from jupiter_handler import jupiter_bot, TOKENS
import solana_tracker
from solana_scanner import scanner
from solana_safety import safety_checker
import sys_logger 
import strategy

POSITIONS_FILE = "solana_positions.json"
TRADE_AMOUNT_SOL = 0.015  # Jumlah SOL per trade
MAX_POSITIONS = 10  # Maksimal posisi bersamaan

STRATEGY_RULES = {
    "SNIPER": {
        # Strategi Judi (JANGAN DIPAKAI DULU)
        "tp_pct": 200.0,
        "sl_pct": -50.0,
        "slippage_bps": 2000
    },
    "TRADER": {
        # Strategi Alpha Hunter (REKOMENDASI)
        "tp_pct": 30.0,     # Ambil profit di 30% (Cukup sering terjadi saat pump)
        "sl_pct": -15.0,    # Cut loss di 15% (Jangan biarkan rugi dalam)
        "slippage_bps": 500, # Slippage 5% (Wajar untuk koin liquid)
        "trailing_stop": True # Aktifkan trailing stop jika nanti sudah profit
    }
}

class SolanaAutoBot:
    def __init__(self):
        self.is_running = False
        self.mode = "MANUAL_TARGET"
        self.strategy = "TRADER"
        self.target_token = "USDC"
        self.target_address = None
        self.target_pair_address = None
        
        self.active_positions = [] 
        self.recently_sold = [] 
        self.load_positions()

    def load_positions(self):
        if os.path.exists(POSITIONS_FILE):
            try:
                with open(POSITIONS_FILE, 'r') as f:
                    data = json.load(f)
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
        self.active_positions = [p for p in self.active_positions if p['token'] != token_symbol]
        self.save_positions()

    def _get_strategy_config(self, strategy_name=None):
        name = (strategy_name or self.strategy or "TRADER").upper()
        return STRATEGY_RULES.get(name, STRATEGY_RULES["TRADER"])

    # --- HELPER: GET DECIMALS (FIX PNL BUG) ---
    async def get_token_decimals(self, address: str):
        """Ambil desimal token langsung dari Blockchain untuk fix kalkulasi."""
        try:
            # Menggunakan client RPC yang sudah ada di safety_checker
            resp = await safety_checker.client.get_token_supply(Pubkey.from_string(address))
            return resp.value.decimals
        except Exception as e:
            # sys_logger.add_log(f"⚠️ Decimals check fail: {e}")
            return 6  # Default fallback untuk memecoins (biasanya 6)

    # --- API HELPER (GeckoTerminal) ---
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
            
            df.ta.rsi(length=14, append=True)
            df.ta.macd(fast=12, slow=26, signal=9, append=True)
            df.ta.bbands(length=20, std=2, append=True)
            
            cols = df.columns
            rsi_col = next((c for c in cols if c.startswith('RSI')), None)
            macd_col = next((c for c in cols if c.startswith('MACD_') and not c.startswith('MACDs')), None)
            sig_col = next((c for c in cols if c.startswith('MACDs_')), None)
            low_bb = next((c for c in cols if c.startswith('BBL_')), None)
            
            if not all([rsi_col, macd_col, sig_col, low_bb]):
                return False, "Indicator calculation failed"

            last = df.iloc[-1]
            votes = []
            
            if last[rsi_col] < 40: votes.append("RSI") 
            if last[macd_col] > last[sig_col]: votes.append("MACD")
            if last['close'] <= last[low_bb] * 1.05: votes.append("BB")
            
            if len(votes) >= 2: return True, f"Strong: {', '.join(votes)}"
            return False, f"Weak ({len(votes)}/3)"
        except Exception as e: return False, str(e)

    # --- LOGIKA UTAMA ---
    async def start(self, mode="MANUAL_TARGET", token_symbol=None, strategy="TRADER"):
        if self.is_running: return
        self.is_running = True
        self.mode = mode
        self.strategy = (strategy or "TRADER").upper()
        if token_symbol: self.target_token = token_symbol
        sys_logger.add_log(f"🚀 AUTO STARTED: {mode} | Strategy: {self.strategy} (Max {MAX_POSITIONS} slots)")
        
        while self.is_running:
            try:
                await self.logic_loop()
            except Exception as e:
                sys_logger.add_log(f"⚠️ Loop Error: {e}")
            await asyncio.sleep(5) 

    def stop(self):
        self.is_running = False
        sys_logger.add_log("🛑 AUTO STOPPED")

    async def logic_loop(self):
        if self.active_positions:
            await self.check_all_exit_conditions()

        current_count = len(self.active_positions)
        if current_count < MAX_POSITIONS:
            if self.mode == "AUTO_DISCOVERY":
                held_tokens = [p['token'] for p in self.active_positions]
                full_ignore_list = self.recently_sold + held_tokens
                
                gem = await scanner.find_gem(ignore_list=full_ignore_list, mode=self.strategy)
                
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
                await self.do_buy()
                self.stop() 

    async def do_buy(self):
        strategy_name = self.strategy
        config = self._get_strategy_config()
        sys_logger.add_log(f"⚔️ Analyzing {self.target_token} | Strategy: {strategy_name}")

        def add_to_ignore(token):
            self.recently_sold.append(token)
            if len(self.recently_sold) > 50: self.recently_sold.pop(0)

        is_safe, reason, _ = await safety_checker.check_token(self.target_address)
        if not is_safe:
            sys_logger.add_log(f"🛑 Unsafe: {reason}")
            if self.mode == "AUTO_DISCOVERY": add_to_ignore(self.target_token)
            return

        if strategy_name == "TRADER":
            candles = await self._fetch_candles(self.target_pair_address)
            if candles is None or len(candles) < 30:
                sys_logger.add_log("⚠️ Not enough candles (<30m)")
                if self.mode == "AUTO_DISCOVERY": add_to_ignore(self.target_token)
                return
                
            is_buy, tech_reason = self._technical_buy_signal(candles)
            if not is_buy:
                sys_logger.add_log(f"⏸️ Technical Skip: {tech_reason}")
                if self.mode == "AUTO_DISCOVERY": add_to_ignore(self.target_token) 
                return
        else:
            sys_logger.add_log("⚡ SNIPER: skipping candle/TA checks, rug-check passed")

        sys_logger.add_log(f"🛒 Executing Buy: {self.target_token} | Slippage {config['slippage_bps']/100:.2f}%")
        # Use address for new tokens not in Jupiter registry, fallback to symbol
        buy_token_param = self.target_address if self.target_address else self.target_token
        quote = await jupiter_bot.get_quote("SOL", buy_token_param, TRADE_AMOUNT_SOL, slippage_bps=config["slippage_bps"])
        
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
                "strategy": strategy_name,
                "txid": result['txid'],
                "timestamp": time.time()
            }
            self.add_position(pos)
            solana_tracker.save_trade(result['txid'], "SOL", self.target_token, TRADE_AMOUNT_SOL, output_amount, token_address=self.target_address)
            sys_logger.add_log(f"✅ BOUGHT {self.target_token}! Holding {len(self.active_positions)}/{MAX_POSITIONS}.")
        else:
            sys_logger.add_log("❌ Swap Failed")

    async def check_all_exit_conditions(self):
        for pos in self.active_positions[:]: 
            await self.check_single_exit(pos)

    async def check_single_exit(self, pos):
        token = pos['token']
        # Use address as priority, fallback to token symbol if address not available
        token_address = pos.get('address') or pos['token']
        amount = pos['token_amount']
        
        # --- FIX DECIMAL MISMATCH (1000x Error) ---
        decimals = await self.get_token_decimals(token_address)
        
        # Jika bot handler mengira 9 desimal (standar SOL) tapi token cuma 6,
        # kita harus menyesuaikan amount yang dikirim agar tidak dianggap 1000x lipat.
        # Formula: Adjusted = RealAmount * (10^Decimals / 10^9)
        adjusted_amount = amount
        if decimals != 9:
             adjusted_amount = amount * (10**decimals) / (10**9)

           # Use token_address for quote (address > symbol fallback)
           # This ensures new tokens not in Jupiter registry can still be quoted after restart
        quote = await jupiter_bot.get_quote(token_address, "SOL", adjusted_amount)
        
        if "error" in quote: return 
        price_per_token = float(quote['output_estimate'].replace(",", ""))
        
        if price_per_token <= 0: return 
        
        current_value_sol = price_per_token # Ini adalah TOTAL SOL (karena kita minta quote all)
        initial_capital = pos['entry_price_sol']
        pnl_pct = ((current_value_sol - initial_capital) / initial_capital) * 100
        
        pos_strategy = (pos.get("strategy") or self.strategy or "TRADER").upper()
        cfg = self._get_strategy_config(pos_strategy)

        should_sell = False
        reason = ""
        
        if pnl_pct >= cfg["tp_pct"]:
            should_sell = True
            reason = f"✅ TP Hit {pos_strategy} (+{pnl_pct:.2f}%)"
        elif pnl_pct <= cfg["sl_pct"]:
            should_sell = True
            reason = f"❌ SL Hit {pos_strategy} ({pnl_pct:.2f}%)"
        
        if should_sell:
            sys_logger.add_log(f"🚨 Selling {token}: {reason}")
            
            # Gunakan adjusted_amount yang sama untuk eksekusi
            # Kita perlu re-fetch quote jika logic swap handler tidak support override amount,
            # tapi execute_swap pakai 'raw_data' dari quote di atas, jadi aman.
            
            res = await jupiter_bot.execute_swap(quote['raw_data'])
            
            if res.get("status") == "success":
                sys_logger.add_log(f"✅ SOLD {token}!")
                solana_tracker.save_trade("SELL", token, "SOL", amount, current_value_sol, status=reason, token_address=token_address)
                self.remove_position(token)
                
                self.recently_sold.append(token)
                if len(self.recently_sold) > 50: self.recently_sold.pop(0)
            else:
                sys_logger.add_log(f"❌ Sell Fail: {res.get('message')}")

solana_auto = SolanaAutoBot()