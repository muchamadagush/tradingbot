# File: backend/solana_auto.py
import asyncio
import json
import os
import time
from jupiter_handler import jupiter_bot, TOKENS
import solana_tracker
from solana_scanner import scanner
import sys_logger # <--- IMPORT LOGGER

POSITIONS_FILE = "solana_positions.json"
TAKE_PROFIT_PCT = 20.0  
STOP_LOSS_PCT = -10.0   
TRADE_AMOUNT_SOL = 0.001 

class SolanaAutoBot:
    def __init__(self):
        self.is_running = False
        self.mode = "MANUAL_TARGET"
        self.target_token = "USDC"
        self.target_address = None
        self.active_position = None
        self.recently_sold = [] 
        self.load_position()

    def load_position(self):
        if os.path.exists(POSITIONS_FILE):
            try:
                with open(POSITIONS_FILE, 'r') as f:
                    data = json.load(f)
                    if data and len(data) > 0: 
                        self.active_position = data[0]
                        sys_logger.add_log(f"📂 Loaded Position: {self.active_position['token']}")
            except: pass

    def save_position(self, pos=None):
        self.active_position = pos
        with open(POSITIONS_FILE, 'w') as f:
            json.dump([pos] if pos else [], f, indent=4)

    async def start(self, mode="MANUAL_TARGET", token_symbol=None):
        if self.is_running: return
        self.is_running = True
        self.mode = mode
        
        sys_logger.add_log(f"🚀 AUTO STARTED: {mode}")
        
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
        if not self.active_position:
            if self.mode == "AUTO_DISCOVERY":
                sys_logger.add_log("📡 Calling Scanner...")
                gem = await scanner.find_gem(ignore_list=self.recently_sold)
                
                if gem:
                    self.target_token = gem['symbol']
                    self.target_address = gem['address']
                    TOKENS[self.target_token] = self.target_address 
                    sys_logger.add_log(f"🎯 Locked: {self.target_token}")
                    await self.do_buy()
                else:
                    sys_logger.add_log("💤 Scanner: No target.")
                    await asyncio.sleep(5)
            else:
                sys_logger.add_log(f"🎯 Manual Target: {self.target_token}")
                await self.do_buy()
        else:
            await self.check_exit_conditions()

    async def do_buy(self):
        sys_logger.add_log(f"⚔️ Buying {self.target_token}...")
        quote = await jupiter_bot.get_quote("SOL", self.target_token, TRADE_AMOUNT_SOL)
        
        if "error" in quote: 
            sys_logger.add_log(f"❌ Buy Failed: {quote['error']}")
            if self.mode == "AUTO_DISCOVERY":
                self.recently_sold.append(self.target_token)
            return
        
        output_amount = float(quote['output_estimate'].replace(",", ""))
        result = await jupiter_bot.execute_swap(quote['raw_data'])
        
        if result.get("status") == "success":
            pos = {
                "token": self.target_token,
                "address": self.target_address if self.target_address else TOKENS.get(self.target_token),
                "entry_price_sol": TRADE_AMOUNT_SOL,
                "token_amount": output_amount,
                "txid": result['txid'],
                "timestamp": time.time()
            }
            self.save_position(pos)
            solana_tracker.save_trade(result['txid'], "SOL", self.target_token, TRADE_AMOUNT_SOL, output_amount)
            sys_logger.add_log("✅ Buy Success! Monitoring...")

    async def check_exit_conditions(self):
        pos = self.active_position
        token = pos['token']
        amount = pos['token_amount']
        
        quote = await jupiter_bot.get_quote(token, "SOL", 1)
        if "error" in quote: 
            if "equal" in str(quote['error']):
                sys_logger.add_log("🗑️ Invalid Position. Deleting.")
                self.save_position(None)
            return

        price_per_token = float(quote['output_estimate'].replace(",", ""))
        current_value_sol = price_per_token * amount
        initial_capital = pos['entry_price_sol']
        pnl_pct = ((current_value_sol - initial_capital) / initial_capital) * 100
        
        # Log PnL (Opsional: Matikan jika terlalu spammy)
        # sys_logger.add_log(f"👀 {token}: PnL {pnl_pct:.2f}%") 

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
            self.save_position(None)
            solana_tracker.save_trade("SELL-TX", token, "SOL", amount, current_value_sol, status=reason)
            
            self.recently_sold.append(token)
            if len(self.recently_sold) > 10: self.recently_sold.pop(0)

            if self.mode == "AUTO_DISCOVERY":
                sys_logger.add_log("🔄 Searching next gem...")
            else:
                self.stop()

solana_auto = SolanaAutoBot()