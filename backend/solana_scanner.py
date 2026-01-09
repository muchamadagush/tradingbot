# File: backend/solana_scanner.py
import aiohttp
import asyncio
import time
import sys_logger 

# KEMBALI KE METODE SEARCH (Lebih variatif daripada cari Token Address)
DEX_API = "https://api.dexscreener.com/latest/dex/search?q=SOL"
WSOL_ADDRESS = "So11111111111111111111111111111111111111112"

# Early Gem Hunter thresholds
MAX_PAIR_AGE_HOURS = 24
MAX_FDV_USD = 100_000
MIN_LIQUIDITY_USD = 1_000

class SolanaScanner:
    async def find_gem(self, ignore_list=[]):
        sys_logger.add_log(f"📡 [SCANNER] Searching 'q=SOL'...")
        
        headers = { "User-Agent": "Mozilla/5.0" }
        
        # Blacklist koin stabil/raksasa
        BLACKLIST_SYMBOLS = ['USDC', 'USDT', 'USDH', 'UXD', 'PAI', 'SOL', 'WSOL', 'USD1', 'USDS', 'MSOL', 'JITOSOL']

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(DEX_API, headers=headers) as response:
                    if response.status != 200: 
                        sys_logger.add_log(f"❌ API Error: {response.status}")
                        return None
                    
                    data = await response.json()
                    pairs = data.get('pairs', [])
                    
                    candidates = []
                    skipped_stable = 0
                    skipped_ignore = 0
                    skipped_age_or_fdv = 0
                    now_ms = int(time.time() * 1000)
                    
                    for p in pairs:
                        # 1. Pastikan di Solana
                        if p.get('chainId') != 'solana': continue

                        base = p.get('baseToken', {})
                        quote = p.get('quoteToken', {})
                        
                        # --- LOGIKA PENENTUAN TARGET ---
                        # Kita mau beli token X menggunakan SOL.
                        # Jadi 'quoteToken' HARUS SOL/WSOL.
                        if quote.get('address') != WSOL_ADDRESS:
                            continue # Skip pair yang bukan pair SOL (misal USDC/WIF)
                        
                        target = base # Target kita adalah Base Token
                        
                        symbol = target.get('symbol', '').upper()
                        address = target.get('address')

                        # --- FILTERING ---
                        
                        # A. Cek Blacklist (Stablecoin)
                        if symbol in BLACKLIST_SYMBOLS: 
                            skipped_stable += 1
                            continue
                        
                        # B. Cek Anti-Loop (Ignore List)
                        if symbol in ignore_list: 
                            skipped_ignore += 1
                            continue

                        # C. Cek Address (Jangan beli SOL palsu yang addressnya sama dengan WSOL)
                        if address == WSOL_ADDRESS:
                            continue

                        # D. Filter Likuiditas (Longgar: $100)
                        liquidity = float(p.get('liquidity', {}).get('usd', 0))
                        volume_24h = float(p.get('volume', {}).get('h24', 0))
                        fdv = float(p.get('fdv', 0) or 0)

                        pair_created_at = p.get('pairCreatedAt') or 0
                        # Dexscreener returns ms epoch
                        pair_age_hours = (now_ms - pair_created_at) / 3_600_000 if pair_created_at else 999

                        # Early gem criteria: young, tiny FDV, enough liquidity to trade
                        if not (pair_age_hours < MAX_PAIR_AGE_HOURS and fdv < MAX_FDV_USD and liquidity > MIN_LIQUIDITY_USD):
                            skipped_age_or_fdv += 1
                            continue

                        if liquidity > MIN_LIQUIDITY_USD and volume_24h > 100:
                            candidates.append({
                                "symbol": symbol,
                                "address": address,
                                "liquidity": liquidity,
                                "volume": volume_24h,
                                "fdv": fdv,
                                "age_hours": pair_age_hours,
                                "url": p['url']
                            })

                    if candidates:
                        # Prioritize youngest gems, then by liquidity
                        candidates.sort(key=lambda x: (x['age_hours'], -x['liquidity'], -x['volume']))
                        best_gem = candidates[0]
                        sys_logger.add_log(
                            f"💎 GEM: {best_gem['symbol']} | Age: {best_gem['age_hours']:.1f}h | FDV: ${best_gem['fdv']:,.0f} | Liq: ${best_gem['liquidity']:,.0f}"
                        )
                        return best_gem
                    
                    # Log detail kenapa kosong
                    sys_logger.add_log(
                        f"⚠️ No Result. Stable: {skipped_stable}, Ignored: {skipped_ignore}, Age/FDV filtered: {skipped_age_or_fdv}"
                    )
                    return None

        except Exception as e:
            sys_logger.add_log(f"❌ Scanner Error: {e}")
            return None

scanner = SolanaScanner()