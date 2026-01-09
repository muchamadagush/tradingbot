# File: backend/solana_auto.py
import asyncio
import json
import os
import time
from datetime import datetime

import aiohttp
import pandas as pd

from jupiter_handler import jupiter_bot, TOKENS
import solana_tracker
from solana_scanner import scanner
import sys_logger # <--- IMPORT LOGGER
import strategy

POSITIONS_FILE = "solana_positions.json"
TAKE_PROFIT_PCT = 20.0  
STOP_LOSS_PCT = -10.0   
TRADE_AMOUNT_SOL = 0.001 

# Rugpull guard thresholds
MAX_HOLDER_PCT = 30.0  # Any single non-LP holder above this is rejected

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

    async def _check_rugpull_risk(self, token_address: str):
        """Basic on-chain safety check using RugCheck API. Rejects if authorities active or holders too concentrated."""
        url = f"https://api.rugcheck.xyz/v1/tokens/{token_address}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=8) as resp:
                    if resp.status != 200:
                        return False, f"RugCheck HTTP {resp.status}"
                    data = await resp.json()
        except Exception as e:
            return False, f"RugCheck error: {e}"

        mint_auth_enabled = data.get("mintAuthorityEnabled", True)
        freeze_auth_enabled = data.get("freezeAuthorityEnabled", True)
        holders = data.get("topHolders", [])

        # Holder concentration: ignore the first holder if it's labeled LP
        risky_holder = None
        for holder in holders:
            if holder.get("isLp"):
                continue
            pct = float(holder.get("percentage", 0) * 100)
            if pct > MAX_HOLDER_PCT:
                risky_holder = pct
                break

        if mint_auth_enabled:
            return False, "Mint authority active"
        if freeze_auth_enabled:
            return False, "Freeze authority active"
        if risky_holder:
            return False, f"Top holder {risky_holder:.1f}% > {MAX_HOLDER_PCT}%"

        return True, "RugCheck passed"

    async def _fetch_candles(self, pair_address: str, interval="5m", limit=120):
        """Fetch OHLCV candles from DexScreener for a pair. Returns DataFrame or None."""
        url = f"https://api.dexscreener.com/latest/dex/candles/solana/{pair_address}?interval={interval}&limit={limit}"
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=8) as resp:
                    if resp.status != 200:
                        return None
                    data = await resp.json()
            candles = data.get("candles") or []
            if not candles:
                return None
            df = pd.DataFrame(candles)
            # DexScreener uses keys o/h/l/c/v with timestamp (ms)
            df = df.rename(columns={"o": "open", "h": "high", "l": "low", "c": "close", "v": "volume"})
            return df
        except Exception as e:
            sys_logger.add_log(f"⚠️ Candle fetch failed: {e}")
            return None

    def _technical_buy_signal(self, df):
        """Reuse strategy votes on custom candle DF. Returns True/False plus reason."""
        try:
            df = df.copy()
            df['RSI'] = strategy.calculate_rsi(df['close'])
            df['MACD'], df['Signal_Line'], _ = strategy.calculate_macd(df['close'])
            df['Upper_BB'], df['Lower_BB'] = strategy.calculate_bollinger_bands(df['close'])

            vote_rsi = strategy.check_rsi_strategy(df)
            vote_macd = strategy.check_macd_strategy(df)
            vote_bb = strategy.check_bb_strategy(df)

            buy_score = sum(1 for v in [vote_rsi, vote_macd, vote_bb] if v == "BUY")
            sell_score = sum(1 for v in [vote_rsi, vote_macd, vote_bb] if v == "SELL")

            if buy_score >= 2 and sell_score == 0:
                return True, f"BUY votes: {buy_score}, SELL votes: {sell_score}"
            return False, f"Signals not strong: BUY {buy_score} / SELL {sell_score}"
        except Exception as e:
            return False, f"Signal error: {e}"

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

        # Anti-rugpull checks (requires address)
        if not self.target_address:
            # Try resolve from TOKENS map for manual targets
            self.target_address = TOKENS.get(self.target_token)
        if not self.target_address:
            sys_logger.add_log("⛔ No token address available; aborting buy")
            return

        ok, reason = await self._check_rugpull_risk(self.target_address)
        if not ok:
            sys_logger.add_log(f"🛑 Rugpull guard blocked buy: {reason}")
            return

        # Technical confirmation using our strategy
        candles = await self._fetch_candles(self.target_address)
        if candles is None or len(candles) < 30:
            sys_logger.add_log("⚠️ Not enough candles for signal; skipping buy")
            return
        tech_ok, tech_reason = self._technical_buy_signal(candles)
        if not tech_ok:
            sys_logger.add_log(f"⏸️ Technical filter: {tech_reason}")
            return
        sys_logger.add_log(f"✅ Technical OK: {tech_reason}")

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
        else:
            sys_logger.add_log("❌ Swap execution failed")

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