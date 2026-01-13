# ==========================================
# File: strategies/solana_sniper.py
# Event-based SNIPER strategy (SAFE)
# ==========================================

import time
from typing import Dict, Tuple


class SolanaSniperStrategy:
    """
    Event-based sniper
    NO TA, NO LOOP BUY
    """

    def __init__(self):
        self.cooldown_tokens = {}
        self.cooldown_seconds = 3600  # 1 jam

    # =========================
    # ENTRY DECISION
    # =========================
    def should_snipe(self, event: Dict) -> Tuple[bool, str]:
        """
        event = {
            token,
            liquidity_sol,
            first_price,
            current_price,
            launch_time
        }
        """

        token = event["token"]
        now = time.time()

        # ---- cooldown ----
        if token in self.cooldown_tokens:
            if now - self.cooldown_tokens[token] < self.cooldown_seconds:
                return False, "Cooldown active"

        # ---- liquidity check ----
        if event["liquidity_sol"] < 5:
            return False, "Low liquidity"

        # ---- delay confirm ----
        if now - event["launch_time"] < 5:
            return False, "Too early"

        # ---- price stability ----
        price_change = (
            (event["current_price"] - event["first_price"])
            / event["first_price"]
        ) * 100

        if abs(price_change) > 25:
            return False, "Price too volatile"

        return True, "SNIPE_OK"

    # =========================
    # POSITION INIT
    # =========================
    def on_buy(self, position: Dict):
        position["sniper_entry_time"] = time.time()
        position["max_price"] = position["entry_price_sol"]

    # =========================
    # EXIT DECISION
    # =========================
    def should_exit(self, position: Dict, market: Dict) -> Tuple[bool, str]:
        """
        Exit logic:
        - Time based
        - Liquidity collapse
        - Fast TP
        """

        now = time.time()
        hold_time = now - position["sniper_entry_time"]

        pnl = position.get("pnl_pct", 0)

        # ---- hard TP ----
        if pnl >= 80:
            return True, "SNIPER_TP_FAST"

        # ---- time exit ----
        if hold_time > 120:
            return True, "SNIPER_TIME_EXIT"

        # ---- liquidity rug ----
        if market.get("liquidity_sol", 999) < 2:
            return True, "SNIPER_LIQUIDITY_DROP"

        return False, "HOLD"

    # =========================
    # POST SELL
    # =========================
    def on_sell(self, position: Dict):
        self.cooldown_tokens[position["token"]] = time.time()
