import asyncio
import json
import os
import time
from typing import List, Dict, Optional

import aiohttp
import pandas as pd
from solders.pubkey import Pubkey

from jupiter_handler import jupiter_bot, TOKENS
import solana_tracker
from solana_scanner import scanner
from solana_safety import safety_checker
import sys_logger

from strategies.solana_trader import SolanaTraderStrategy
from risk_manager import RiskManager, BotType, BOT_RISK_PROFILES


# =============================
# CONFIG
# =============================
POSITIONS_FILE = "solana_positions.json"
MAX_POSITIONS = 3  # Max 3 concurrent positions per P2
CANDLE_LIMIT = 120

# Position Sizing Config (P2 Fix)
POSITION_SIZE_PCT = 0.015  # 1.5% of portfolio per trade
DEFAULT_SOL_BALANCE = 1.0  # Fallback if balance fetch fails
MIN_TRADE_SOL = 0.01       # Minimum trade size
MAX_TRADE_SOL = 0.1        # Maximum trade size (safety cap)

# Trailing Stop Config
TRAILING_STOP_ACTIVATION_PCT = 10.0  # Activate after 10% profit
TRAILING_STOP_DISTANCE_PCT = 5.0     # Trail 5% behind high water mark


# =============================
# SOLANA AUTO BOT
# =============================
class SolanaAutoBot:
    def __init__(self):
        self.is_running = False
        self.mode = "MANUAL_TARGET"
        self.strategy_name = "TRADER"

        self.target_token: Optional[str] = None
        self.target_address: Optional[str] = None
        self.target_pair_address: Optional[str] = None

        self.active_positions: List[Dict] = []
        self.recently_sold: List[str] = []

        self.trader_strategy = SolanaTraderStrategy()
        
        # Track SOL balance for percentage-based sizing
        self.cached_sol_balance = DEFAULT_SOL_BALANCE
        
        # NEW: Trailing stop state per token
        # {token: {"high_water_mark": float, "trailing_active": bool}}
        self.trailing_stop_state: Dict[str, Dict] = {}
        
        # NEW: Per-bot risk manager for Trader
        self.risk_manager = RiskManager(
            initial_balance=100.0,  # SOL balance estimate
            bot_type=BotType.TRADER
        )
        
        self.load_positions()

    # =============================
    # POSITION STORAGE
    # =============================
    def load_positions(self):
        if not os.path.exists(POSITIONS_FILE):
            self.active_positions = []
            return

        try:
            with open(POSITIONS_FILE, "r") as f:
                data = json.load(f)
                self.active_positions = data if isinstance(data, list) else []
            sys_logger.add_log(f"📂 Loaded {len(self.active_positions)} positions")
        except Exception as e:
            sys_logger.add_log(f"⚠️ Position load failed: {e}")
            self.active_positions = []

    def save_positions(self):
        with open(POSITIONS_FILE, "w") as f:
            json.dump(self.active_positions, f, indent=4)

    def add_position(self, pos: Dict):
        self.active_positions.append(pos)
        self.save_positions()

    def remove_position(self, token: str):
        self.active_positions = [
            p for p in self.active_positions if p["token"] != token
        ]
        self.save_positions()

    # =============================
    # SOL BALANCE FOR POSITION SIZING (P2 FIX)
    # =============================
    async def refresh_sol_balance(self) -> float:
        """Fetch current SOL balance for percentage-based position sizing."""
        try:
            balances = await jupiter_bot.get_all_balances()
            if balances and isinstance(balances, dict):
                sol_balance = balances.get("SOL", 0)
                if sol_balance > 0:
                    self.cached_sol_balance = sol_balance
                    return sol_balance
        except Exception as e:
            sys_logger.add_log(f"⚠️ Balance fetch failed: {e}")
        return self.cached_sol_balance
    
    def calculate_position_size(self, balance: float) -> float:
        """Calculate position size as percentage of portfolio (P2 Fix)."""
        size = balance * POSITION_SIZE_PCT
        # Apply min/max caps for safety
        size = max(MIN_TRADE_SOL, min(MAX_TRADE_SOL, size))
        return round(size, 6)

    # =============================
    # TOKEN DECIMALS (CRITICAL FIX)
    # =============================
    async def get_token_decimals(self, address: str) -> int:
        try:
            resp = await safety_checker.client.get_token_supply(
                Pubkey.from_string(address)
            )
            return int(resp.value.decimals)
        except Exception:
            # fallback memecoin
            return 6

    # =============================
    # MARKET DATA (GECKOTERMINAL)
    # =============================
    async def _fetch_candles(self, pool_id: str, limit: int = CANDLE_LIMIT):
        url = (
            "https://api.geckoterminal.com/api/v2/"
            f"networks/solana/pools/{pool_id}/ohlcv/minute"
            f"?limit={limit}"
        )

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, timeout=10) as resp:
                    if resp.status != 200:
                        sys_logger.add_log(f"❌ Candle HTTP {resp.status}")
                        return None
                    data = await resp.json()

            rows = data["data"]["attributes"]["ohlcv_list"]
            df = pd.DataFrame(
                rows,
                columns=["ts", "open", "high", "low", "close", "volume"]
            )
            df.sort_values("ts", inplace=True)
            df.reset_index(drop=True, inplace=True)
            return df

        except Exception as e:
            sys_logger.add_log(f"❌ Candle fetch error: {e}")
            return None

    # =============================
    # MAIN LOOP
    # =============================
    async def start(self, mode="MANUAL_TARGET", token_symbol=None):
        if self.is_running:
            return

        self.is_running = True
        self.mode = mode

        if token_symbol:
            self.target_token = token_symbol

        sys_logger.add_log(
            f"🚀 AUTO STARTED | Mode={mode} Strategy=SOLANA_TRADER"
        )

        while self.is_running:
            try:
                await self.logic_loop()
            except Exception as e:
                sys_logger.add_log(f"⚠️ Loop error: {e}")
            await asyncio.sleep(5)

    def stop(self):
        self.is_running = False
        sys_logger.add_log("🛑 AUTO STOPPED")

    # =============================
    # CORE LOGIC
    # =============================
    async def logic_loop(self):
        # ---- exit management ----
        if self.active_positions:
            await self.check_all_exit_conditions()

        # ---- RISK CHECK ----
        if not self.risk_manager.can_trade_new():
            if self.risk_manager.is_in_cooldown():
                remaining = self.risk_manager.get_cooldown_remaining()
                sys_logger.add_log(f"⏸️ Trader cooldown: {remaining}s remaining")
            else:
                sys_logger.add_log("⚠️ Trader risk limit reached")
            return

        if len(self.active_positions) >= MAX_POSITIONS:
            return

        # ---- AUTO DISCOVERY ----
        if self.mode == "AUTO_DISCOVERY":
            ignore = self.recently_sold + [
                p["token"] for p in self.active_positions
            ]

            gem = await scanner.find_gem(
                ignore_list=ignore,
                mode="TRADER"
            )

            if not gem:
                return

            self.target_token = gem["symbol"]
            self.target_address = gem["address"]
            self.target_pair_address = gem["pair_address"]

            TOKENS[self.target_token] = self.target_address

            await self.do_buy()

        # ---- MANUAL ----
        elif self.mode == "MANUAL_TARGET" and not self.active_positions:
            await self.do_buy()
            self.stop()

    # =============================
    # BUY LOGIC
    # =============================
    async def do_buy(self):
        if not all([
            self.target_token,
            self.target_address,
            self.target_pair_address
        ]):
            sys_logger.add_log("❌ Target not fully defined")
            return

        sys_logger.add_log(f"⚔️ Analyzing {self.target_token}")

        # ---- SAFETY CHECK ----
        is_safe, reason, _ = await safety_checker.check_token(
            self.target_address
        )
        if not is_safe:
            sys_logger.add_log(f"🛑 Unsafe token: {reason}")
            return

        # ---- CANDLES ----
        candles = await self._fetch_candles(self.target_pair_address)
        if candles is None or candles.empty:
            return

        # ---- STRATEGY ----
        should_buy, reason = self.trader_strategy.should_buy({
            "token": self.target_token,
            "df": candles
        })

        if not should_buy:
            sys_logger.add_log(f"⏸️ Skip {self.target_token}: {reason}")
            return

        # ---- PERCENTAGE-BASED POSITION SIZING (P2 FIX) ----
        sol_balance = await self.refresh_sol_balance()
        trade_amount = self.calculate_position_size(sol_balance)
        sys_logger.add_log(f"💰 Position size: {trade_amount:.4f} SOL ({POSITION_SIZE_PCT*100}% of {sol_balance:.4f})")

        # ---- JUPITER QUOTE WITH FRESHNESS VALIDATION ----
        QUOTE_MAX_AGE_SECONDS = 5  # Quote expires after 5 seconds
        MAX_PRICE_DEVIATION_PCT = 2.0  # Max 2% price deviation
        MAX_REQUOTE_ATTEMPTS = 3
        
        quote = None
        for attempt in range(MAX_REQUOTE_ATTEMPTS):
            quote = await jupiter_bot.get_quote(
                "SOL",
                self.target_address,
                trade_amount,
                slippage_bps=500
            )

            if "error" in quote:
                sys_logger.add_log(f"❌ Quote error: {quote['error']}")
                return
            
            # Validate quote freshness
            quote_age = time.time() - quote.get("quote_timestamp", 0)
            if quote_age > QUOTE_MAX_AGE_SECONDS:
                sys_logger.add_log(f"⚠️ Quote expired ({quote_age:.1f}s > {QUOTE_MAX_AGE_SECONDS}s), re-quoting... ({attempt+1}/{MAX_REQUOTE_ATTEMPTS})")
                await asyncio.sleep(0.5)  # Brief pause before retry
                continue
            
            # Quote is fresh, proceed
            break
        else:
            sys_logger.add_log(f"❌ Failed to get fresh quote after {MAX_REQUOTE_ATTEMPTS} attempts")
            return
        
        # Log quote details
        effective_price = quote.get("effective_price", 0)
        sys_logger.add_log(f"📊 Quote: {trade_amount:.4f} SOL → {quote['output_estimate']} {self.target_token} (price: {effective_price:.6f})")

        # ---- EXECUTE BUY ----
        res = await jupiter_bot.execute_swap(quote["raw_data"])
        if res.get("status") != "success":
            sys_logger.add_log("❌ Buy failed")
            return

        output_amt = float(quote["output_estimate"].replace(",", ""))

        pos = {
            "token": self.target_token,
            "address": self.target_address,
            "pair_address": self.target_pair_address,
            "token_amount": output_amt,
            "entry_price_sol": trade_amount,  # Use actual trade amount
            "entry_time": time.time(),
            "strategy": "SOLANA_TRADER",
            "tp1_hit": False,
            "txid": res["txid"]
        }

        self.trader_strategy.on_buy(pos)
        self.add_position(pos)

        solana_tracker.save_trade(
            res["txid"],
            "SOL",
            self.target_token,
            trade_amount,  # Use actual trade amount
            output_amt,
            token_address=self.target_address
        )

        sys_logger.add_log(f"✅ BOUGHT {self.target_token} for {trade_amount:.4f} SOL")

    # =============================
    # SELL LOGIC
    # =============================
    async def check_all_exit_conditions(self):
        for pos in self.active_positions[:]:
            await self.check_single_exit(pos)

    async def check_single_exit(self, pos: Dict):
        token = pos["token"]
        address = pos["address"]
        amount = pos["token_amount"]

        decimals = await self.get_token_decimals(address)

        # Jupiter expects raw token amount
        adjusted_amount = (
            amount * (10 ** decimals) / (10 ** 9)
            if decimals != 9 else amount
        )

        quote = await jupiter_bot.get_quote(
            address,
            "SOL",
            adjusted_amount
        )

        if "error" in quote:
            return

        current_sol = float(quote["output_estimate"].replace(",", ""))
        entry = pos["entry_price_sol"]
        pnl_pct = ((current_sol - entry) / entry) * 100

        pos["pnl_pct"] = pnl_pct
        
        # ========== TRAILING STOP LOGIC ==========
        trailing_exit = False
        trailing_reason = ""
        
        # Initialize trailing state for this token
        if token not in self.trailing_stop_state:
            self.trailing_stop_state[token] = {
                "high_water_mark": current_sol,
                "trailing_active": False
            }
        
        ts_state = self.trailing_stop_state[token]
        
        # Update high water mark
        if current_sol > ts_state["high_water_mark"]:
            ts_state["high_water_mark"] = current_sol
        
        # Activate trailing stop when profit reaches threshold
        if pnl_pct >= TRAILING_STOP_ACTIVATION_PCT and not ts_state["trailing_active"]:
            ts_state["trailing_active"] = True
            sys_logger.add_log(f"🎯 {token}: Trailing stop activated at {pnl_pct:.1f}%")
        
        # Check if trailing stop hit
        if ts_state["trailing_active"]:
            hwm = ts_state["high_water_mark"]
            trailing_stop_price = hwm * (1 - TRAILING_STOP_DISTANCE_PCT / 100)
            
            if current_sol <= trailing_stop_price:
                trailing_exit = True
                hwm_pnl = ((hwm - entry) / entry) * 100
                trailing_reason = f"TRAILING_STOP (peak {hwm_pnl:.1f}%, now {pnl_pct:.1f}%)"
        
        # ========== STRATEGY-BASED EXIT ==========
        should_sell, reason = self.trader_strategy.should_sell(
            pos,
            market={}
        )
        
        # Use trailing stop exit if triggered, otherwise use strategy exit
        if trailing_exit:
            should_sell = True
            reason = trailing_reason

        if not should_sell:
            return

        sys_logger.add_log(f"🚨 SELL {token}: {reason}")

        res = await jupiter_bot.execute_swap(quote["raw_data"])
        if res.get("status") != "success":
            sys_logger.add_log("❌ Sell failed")
            return

        # Calculate PnL in SOL terms
        pnl_sol = current_sol - entry
        
        solana_tracker.save_trade(
            "SELL",
            token,
            "SOL",
            amount,
            current_sol,
            status=reason,
            token_address=address
        )

        self.trader_strategy.on_sell(pos)
        self.remove_position(token)
        
        # Cleanup trailing stop state
        if token in self.trailing_stop_state:
            del self.trailing_stop_state[token]
        
        # Record PnL to risk manager (for cooldown tracking)
        self.risk_manager.record_trade_pnl(pnl_sol)

        self.recently_sold.append(token)
        self.recently_sold = self.recently_sold[-50:]

        sys_logger.add_log(f"✅ SOLD {token} | PnL: {pnl_sol:.4f} SOL")


# =============================
# SINGLETON
# =============================
solana_auto = SolanaAutoBot()
