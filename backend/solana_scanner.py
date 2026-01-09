# File: backend/solana_scanner.py
import aiohttp
import asyncio
import time
import sys_logger 

# STRATEGI BARU: Latest Token Profiles (Fokus pada Token Fresh)
# Endpoint untuk mendapatkan profil token terbaru yang sudah diverifikasi
PROFILES_API = "https://api.dexscreener.com/token-profiles/latest/v1"
TOKENS_API = "https://api.dexscreener.com/latest/dex/tokens/"
WSOL_ADDRESS = "So11111111111111111111111111111111111111112"

# Early Gem Hunter thresholds
MAX_PAIR_AGE_HOURS = 72  # 3 days - longgarkan untuk tangkap lebih banyak peluang
MAX_FDV_USD = 500_000  # $500k - naikkan batas untuk token yang agak mature
MIN_LIQUIDITY_USD = 1_000

class SolanaScanner:
    async def find_gem(self, ignore_list=[]):
        sys_logger.add_log(f"📡 [SCANNER] Scanning Latest Profiles...")
        
        headers = { "User-Agent": "Mozilla/5.0" }
        
        # Blacklist koin stabil/raksasa
        BLACKLIST_SYMBOLS = ['USDC', 'USDT', 'USDH', 'UXD', 'PAI', 'SOL', 'WSOL', 'USD1', 'USDS', 'MSOL', 'JITOSOL']

        try:
            async with aiohttp.ClientSession() as session:
                # === LANGKAH 1: FETCH LATEST TOKEN PROFILES ===
                async with session.get(PROFILES_API, headers=headers) as response:
                    if response.status != 200: 
                        sys_logger.add_log(f"❌ Profiles API Error: {response.status}")
                        return None
                    
                    profiles_data = await response.json()
                    all_profiles = profiles_data if isinstance(profiles_data, list) else []
                    print(f"DEBUG: Found {len(all_profiles)} total profiles")
                
                # === LANGKAH 2: FILTER SOLANA CHAIN ===
                solana_addresses = []
                for profile in all_profiles:
                    if profile.get('chainId') == 'solana':
                        addr = profile.get('tokenAddress')
                        if addr and addr != WSOL_ADDRESS:
                            solana_addresses.append(addr)
                
                # Batasi maksimal 30 address untuk batch request
                solana_addresses = solana_addresses[:30]
                print(f"DEBUG: Found {len(solana_addresses)} Solana tokens")
                
                if not solana_addresses:
                    sys_logger.add_log(f"⚠️ No Solana tokens in latest profiles")
                    return None
                
                # === LANGKAH 3: BATCH FETCH TOKEN DETAILS ===
                batch_addresses = ",".join(solana_addresses)
                tokens_url = f"{TOKENS_API}{batch_addresses}"
                
                async with session.get(tokens_url, headers=headers) as response:
                    if response.status != 200:
                        sys_logger.add_log(f"❌ Tokens API Error: {response.status}")
                        return None
                    
                    tokens_data = await response.json()
                    all_pairs = tokens_data.get('pairs', [])
                    print(f"DEBUG: Fetched {len(all_pairs)} pairs from batch")
                
                # === LANGKAH 4: FINAL FILTERING ===
                candidates = []
                skipped_quote = 0
                skipped_old = 0
                skipped_expensive = 0
                skipped_stable = 0
                skipped_ignore = 0
                skipped_liquidity = 0
                now_ms = int(time.time() * 1000)
                
                for p in all_pairs:
                    # Pastikan di Solana
                    if p.get('chainId') != 'solana': continue
                    
                    base = p.get('baseToken', {})
                    quote = p.get('quoteToken', {})
                    
                    # Ambil Pair Address (diperlukan untuk fetch candle)
                    pair_address = p.get('pairAddress')
                    
                    # --- CEK QUOTE (HARUS SOL/WSOL) ---
                    if quote.get('address') != WSOL_ADDRESS:
                        skipped_quote += 1
                        continue
                    
                    target = base
                    symbol = target.get('symbol', '').upper()
                    address = target.get('address')
                    
                    # --- CEK BLACKLIST (STABLECOIN) ---
                    if symbol in BLACKLIST_SYMBOLS: 
                        skipped_stable += 1
                        continue
                    
                    # --- CEK AGE/FDV ---
                    pair_created_at = p.get('pairCreatedAt') or 0
                    pair_age_hours = (now_ms - pair_created_at) / 3_600_000 if pair_created_at else 999
                    fdv = float(p.get('fdv', 0) or 0)
                    
                    # Cek Umur (max 72 jam = 3 hari)
                    if pair_age_hours > 72:
                        skipped_old += 1
                        continue
                    
                    # Cek Harga (FDV max $500k)
                    if fdv > 500000:
                        skipped_expensive += 1
                        continue
                    
                    # Anti-Loop (Ignore List)
                    if symbol in ignore_list: 
                        skipped_ignore += 1
                        continue
                    
                    # Cek Address
                    if address == WSOL_ADDRESS:
                        continue
                    
                    # --- CEK LIKUIDITAS ---
                    liquidity = float(p.get('liquidity', {}).get('usd', 0))
                    volume_24h = float(p.get('volume', {}).get('h24', 0))
                    
                    if liquidity < MIN_LIQUIDITY_USD:
                        skipped_liquidity += 1
                        continue
                    
                    if volume_24h > 100:
                        candidates.append({
                            "symbol": symbol,
                            "address": address,
                            "pair_address": pair_address,
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
                    f"⚠️ No Result. QuoteSkip: {skipped_quote}, Old: {skipped_old}, Expensive: {skipped_expensive}, Stable: {skipped_stable}, Liquidity: {skipped_liquidity}, Ignored: {skipped_ignore}"
                )
                return None

        except Exception as e:
            sys_logger.add_log(f"❌ Scanner Error: {e}")
            return None

scanner = SolanaScanner()
