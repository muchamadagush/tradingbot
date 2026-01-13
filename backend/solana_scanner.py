import aiohttp
import time
import sys_logger

from utils.gecko_pool_resolver import resolve_best_pool


# =========================
# API CONFIG
# =========================
PROFILES_API = "https://api.dexscreener.com/token-profiles/latest/v1"
TOKENS_API = "https://api.dexscreener.com/latest/dex/tokens/"
WSOL_ADDRESS = "So11111111111111111111111111111111111111112"


class SolanaScanner:
    async def find_gem(self, ignore_list=None, mode="SNIPER"):
        ignore_list = ignore_list or []
        mode = (mode or "SNIPER").upper()

        sys_logger.add_log(f"📡 [SCANNER] Scanning Latest Profiles ({mode})...")

        headers = {"User-Agent": "Mozilla/5.0"}

        BLACKLIST_SYMBOLS = [
            "USDC", "USDT", "USDH", "UXD", "PAI",
            "SOL", "WSOL", "USD1", "USDS",
            "MSOL", "JITOSOL", "JUP", "RAY"
        ]

        try:
            async with aiohttp.ClientSession() as session:

                # =====================================================
                # STEP 1 — FETCH LATEST TOKEN PROFILES
                # =====================================================
                async with session.get(PROFILES_API, headers=headers) as resp:
                    if resp.status != 200:
                        sys_logger.add_log(f"❌ Profiles API Error: {resp.status}")
                        return None

                    profiles = await resp.json()
                    profiles = profiles if isinstance(profiles, list) else []

                # =====================================================
                # STEP 2 — FILTER SOLANA TOKENS
                # =====================================================
                solana_addresses = []
                for p in profiles:
                    if p.get("chainId") == "solana":
                        addr = p.get("tokenAddress")
                        if addr and addr != WSOL_ADDRESS:
                            solana_addresses.append(addr)

                solana_addresses = solana_addresses[:30]

                if not solana_addresses:
                    sys_logger.add_log("⚠️ No Solana tokens found")
                    return None

                # =====================================================
                # STEP 3 — FETCH TOKEN DETAILS
                # =====================================================
                tokens_url = TOKENS_API + ",".join(solana_addresses)
                async with session.get(tokens_url, headers=headers) as resp:
                    if resp.status != 200:
                        sys_logger.add_log(f"❌ Tokens API Error: {resp.status}")
                        return None

                    data = await resp.json()
                    all_pairs = data.get("pairs", [])

                # =====================================================
                # STEP 4 — FILTERING LOGIC
                # =====================================================
                candidates = []

                skipped_quote = 0
                skipped_age = 0
                skipped_fdv = 0
                skipped_stable = 0
                skipped_ignore = 0
                skipped_liquidity = 0
                skipped_volume = 0
                skipped_trend = 0
                skipped_gecko = 0

                now_ms = int(time.time() * 1000)

                for p in all_pairs:
                    if p.get("chainId") != "solana":
                        continue

                    base = p.get("baseToken", {})
                    quote = p.get("quoteToken", {})

                    if quote.get("address") != WSOL_ADDRESS:
                        skipped_quote += 1
                        continue

                    symbol = (base.get("symbol") or "").upper()
                    address = base.get("address")

                    if not address:
                        continue

                    if symbol in BLACKLIST_SYMBOLS:
                        skipped_stable += 1
                        continue

                    if symbol in ignore_list:
                        skipped_ignore += 1
                        continue

                    pair_created_at = p.get("pairCreatedAt") or 0
                    age_ms = now_ms - pair_created_at if pair_created_at else 0
                    age_minutes = age_ms / 60_000
                    age_hours = age_minutes / 60

                    liquidity = float(p.get("liquidity", {}).get("usd", 0))
                    volume_24h = float(p.get("volume", {}).get("h24", 0))
                    volume_h1 = float(p.get("volume", {}).get("h1", 0))
                    fdv = float(p.get("fdv") or 0)
                    price_change_h1 = float(p.get("priceChange", {}).get("h1", 0))

                    # =============================
                    # MODE LOGIC
                    # =============================
                    if mode == "SNIPER":
                        if age_minutes > 15:
                            skipped_age += 1
                            continue
                        if liquidity < 2000:
                            skipped_liquidity += 1
                            continue
                        if fdv > 500_000:
                            skipped_fdv += 1
                            continue
                    else:
                        if age_minutes < 30:
                            skipped_age += 1
                            continue
                        if liquidity < 5000:
                            skipped_liquidity += 1
                            continue
                        if volume_h1 < 5000:
                            skipped_volume += 1
                            continue
                        if price_change_h1 <= 0:
                            skipped_trend += 1
                            continue

                    # =====================================================
                    # 🔥 RESOLVE GECKOTERMINAL POOL (CRITICAL FIX)
                    # =====================================================
                    pool_id = resolve_best_pool(address)
                    if not pool_id:
                        skipped_gecko += 1
                        continue

                    candidates.append({
                        "symbol": symbol,
                        "address": address,
                        "pair_address": pool_id,   # ✅ FINAL OUTPUT
                        "liquidity": liquidity,
                        "volume_h1": volume_h1,
                        "volume": volume_24h,
                        "fdv": fdv,
                        "price_change_h1": price_change_h1,
                        "age_minutes": age_minutes,
                        "age_hours": age_hours,
                        "url": p.get("url")
                    })

                # =====================================================
                # STEP 5 — SORT & PICK
                # =====================================================
                if candidates:
                    if mode == "SNIPER":
                        candidates.sort(key=lambda x: x["liquidity"], reverse=True)
                    else:
                        candidates.sort(key=lambda x: x["volume_h1"], reverse=True)

                    best = candidates[0]
                    age_label = f"{best['age_minutes']:.1f}m" if best["age_minutes"] < 60 else f"{best['age_hours']:.2f}h"
                    trend = best.get("price_change_h1", 0)

                    sys_logger.add_log(
                        f"💎 GEM ({mode}) {best['symbol']} | Age {age_label} | "
                        f"Liq ${best['liquidity']:,.0f} | Vol1h ${best['volume_h1']:,.0f} | "
                        f"Trend {trend}% | Pool {best['pair_address']}"
                    )
                    return best

                sys_logger.add_log(
                    f"⚠️ No Result ({mode}) | "
                    f"Quote={skipped_quote} Age={skipped_age} FDV={skipped_fdv} "
                    f"Stable={skipped_stable} Liq={skipped_liquidity} "
                    f"Vol={skipped_volume} Trend={skipped_trend} "
                    f"GeckoFail={skipped_gecko} Ignored={skipped_ignore}"
                )
                return None

        except Exception as e:
            sys_logger.add_log(f"❌ Scanner Error: {e}")
            return None


scanner = SolanaScanner()
