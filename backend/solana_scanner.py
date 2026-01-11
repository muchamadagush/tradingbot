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

class SolanaScanner:
    async def find_gem(self, ignore_list=None, mode="SNIPER"):
        ignore_list = ignore_list or []
        mode = (mode or "SNIPER").upper()
        
        sys_logger.add_log(f"📡 [SCANNER] Scanning Latest Profiles ({mode})...")
        
        headers = { "User-Agent": "Mozilla/5.0" }
        
        # Blacklist koin stabil/raksasa agar tidak salah beli
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
                
                # === LANGKAH 2: FILTER SOLANA CHAIN ===
                solana_addresses = []
                for profile in all_profiles:
                    if profile.get('chainId') == 'solana':
                        addr = profile.get('tokenAddress')
                        if addr and addr != WSOL_ADDRESS:
                            solana_addresses.append(addr)
                
                # Batasi maksimal 30 address untuk batch request (Limit API DexScreener)
                solana_addresses = solana_addresses[:30]
                
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
                
                # === LANGKAH 4: FINAL FILTERING ===
                candidates = []
                
                # Counter untuk Debugging Log
                skipped_quote = 0
                skipped_age = 0
                skipped_fdv = 0
                skipped_stable = 0
                skipped_ignore = 0
                skipped_liquidity = 0
                skipped_volume = 0
                
                now_ms = int(time.time() * 1000)
                
                for p in all_pairs:
                    # 1. Pastikan Chain Solana
                    if p.get('chainId') != 'solana': continue
                    
                    base = p.get('baseToken', {})
                    quote = p.get('quoteToken', {})
                    
                    # Ambil Pair Address (Penting untuk fetch candle nanti)
                    pair_address = p.get('pairAddress')
                    
                    # 2. Cek Quote Token (HARUS SOL/WSOL)
                    if quote.get('address') != WSOL_ADDRESS:
                        skipped_quote += 1
                        continue
                    
                    symbol = base.get('symbol', '').upper()
                    address = base.get('address')
                    
                    # 3. Cek Blacklist & Ignore List
                    if symbol in BLACKLIST_SYMBOLS: 
                        skipped_stable += 1
                        continue
                    if symbol in ignore_list: 
                        skipped_ignore += 1
                        continue

                    # 4. Ambil Data Metrik
                    pair_created_at = p.get('pairCreatedAt') or 0
                    pair_age_ms = now_ms - pair_created_at if pair_created_at else 0
                    pair_age_hours = pair_age_ms / 3_600_000
                    pair_age_minutes = pair_age_ms / 60_000
                    
                    liquidity = float(p.get('liquidity', {}).get('usd', 0))
                    volume_24h = float(p.get('volume', {}).get('h24', 0))
                    fdv = float(p.get('fdv', 0) or 0)
                    
                    # 5. LOGIKA FILTER BERDASARKAN MODE
                    if mode == "SNIPER":
                        # --- MODE SNIPER (AGGRESSIVE - Cari Bayi Baru) ---
                        # Umur: Harus < 5 menit (LEBIH AGRESIF)
                        if pair_age_minutes > 5.0:
                            skipped_age += 1
                            continue
                        # Market Cap: Harus < $100k (lebih agresif tetapi tetap selektif)
                        if pair_age_minutes < 2.0:
                            if fdv > 100_000:
                                skipped_fdv += 1
                                continue
                            # Likuiditas turun menjadi $200 untuk token super fresh (< 2 menit)
                            if liquidity < 200:
                                skipped_liquidity += 1
                                continue
                        else:
                            # Untuk token 2-5 menit, FDV bisa sampai $100k, likuiditas $500
                            if fdv > 100_000:
                                skipped_fdv += 1
                                continue
                            if liquidity < 500:
                                skipped_liquidity += 1
                                continue
                            
                    else:
                        # --- MODE TRADER (Cari Volume) ---
                        # Umur: Bebas (asal valid profile), tapi kita skip yang baru lahir < 1 jam biar aman
                        if pair_age_hours < 1.0:
                            skipped_age += 1
                            continue
                        # Likuiditas: Minimal $10,000 (Lebih tebal)
                        if liquidity < 10_000:
                            skipped_liquidity += 1
                            continue
                        # Volume: Minimal $10,000 (Harus aktif)
                        if volume_24h < 10_000:
                            skipped_volume += 1
                            continue

                    # Jika lolos semua filter, masukkan kandidat
                    candidates.append({
                        "symbol": symbol,
                        "address": address,
                        "pair_address": pair_address,
                        "liquidity": liquidity,
                        "volume": volume_24h,
                        "fdv": fdv,
                        "age_hours": pair_age_hours,
                        "age_minutes": pair_age_minutes,
                        "url": p['url']
                    })
                
                # === LANGKAH 5: SORTING & SELECTION ===
                if candidates:
                    if mode == "SNIPER":
                        # Sniper: AGGRESSIVE SORTING
                        # Prioritas 1: Umur < 1 menit (SUPER PRIORITY) di paling atas
                        # Prioritas 2: Sisa koin diurutkan dari termuda
                        super_fresh = [c for c in candidates if c['age_minutes'] < 1.0]
                        other_fresh = [c for c in candidates if c['age_minutes'] >= 1.0]
                        
                        # Sort super fresh by age (termuda duluan)
                        super_fresh.sort(key=lambda x: (x['age_minutes'], -x['liquidity']))
                        # Sort other fresh by age
                        other_fresh.sort(key=lambda x: (x['age_minutes'], -x['liquidity']))
                        
                        # Gabung: super fresh duluan, baru yang lain
                        candidates = super_fresh + other_fresh
                    else:
                        # Trader: Prioritas Volume Tertinggi
                        candidates.sort(key=lambda x: (-x['volume'], -x['liquidity']))
                        
                    best_gem = candidates[0]
                    age_label = f"{best_gem['age_minutes']:.1f}m" if best_gem['age_minutes'] < 60 else f"{best_gem['age_hours']:.2f}h"
                    sys_logger.add_log(
                        f"💎 GEM ({mode}): {best_gem['symbol']} | Age: {age_label} | FDV: ${best_gem['fdv']:,.0f} | Liq: ${best_gem['liquidity']:,.0f}"
                    )
                    return best_gem
                
                # Log detail kenapa kosong (Untuk Debugging)
                sys_logger.add_log(
                    f"⚠️ No Result ({mode}). QuoteSkip: {skipped_quote}, Age: {skipped_age}, FDV: {skipped_fdv}, Stable: {skipped_stable}, Liq: {skipped_liquidity}, Vol: {skipped_volume}, Ignored: {skipped_ignore}"
                )
                return None

        except Exception as e:
            sys_logger.add_log(f"❌ Scanner Error: {e}")
            return None

scanner = SolanaScanner()
