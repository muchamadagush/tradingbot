# File: backend/solana_scanner.py
import aiohttp
import asyncio
import time
import sys_logger 

# STRATEGI BARU: Latest Token Profiles (Fokus pada Token Fresh & Trending)
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
        BLACKLIST_SYMBOLS = ['USDC', 'USDT', 'USDH', 'UXD', 'PAI', 'SOL', 'WSOL', 'USD1', 'USDS', 'MSOL', 'JITOSOL', 'JUP', 'RAY']

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
                
                # Counter untuk Debugging Log (Dijaga agar tidak hilang)
                skipped_quote = 0
                skipped_age = 0
                skipped_fdv = 0
                skipped_stable = 0
                skipped_ignore = 0
                skipped_liquidity = 0
                skipped_volume = 0
                skipped_trend = 0  # Counter baru untuk trend
                
                now_ms = int(time.time() * 1000)
                
                for p in all_pairs:
                    # 1. Pastikan Chain Solana
                    if p.get('chainId') != 'solana': continue
                    
                    base = p.get('baseToken', {})
                    quote = p.get('quoteToken', {})
                    pair_address = p.get('pairAddress') # Penting
                    
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

                    # 4. Ambil Data Metrik (Ditambah Metric Baru)
                    pair_created_at = p.get('pairCreatedAt') or 0
                    pair_age_ms = now_ms - pair_created_at if pair_created_at else 0
                    pair_age_hours = pair_age_ms / 3_600_000
                    pair_age_minutes = pair_age_ms / 60_000
                    
                    liquidity = float(p.get('liquidity', {}).get('usd', 0))
                    volume_24h = float(p.get('volume', {}).get('h24', 0))
                    volume_h1 = float(p.get('volume', {}).get('h1', 0)) # Metric Baru
                    fdv = float(p.get('fdv', 0) or 0)
                    price_change_h1 = float(p.get('priceChange', {}).get('h1', 0)) # Metric Baru (Trend)
                    
                    # 5. LOGIKA FILTER BERDASARKAN MODE (UPDATED STRATEGY)
                    if mode == "SNIPER":
                        # --- MODE SNIPER (Updated: Lebih Aman) ---
                        # Umur: Maksimal 15 menit (Jangan terlalu bayi < 2 menit, terlalu berisiko rugpull)
                        if pair_age_minutes > 15.0:
                            skipped_age += 1
                            continue
                        
                        # Likuiditas: Minimal $2,000 (Dinaikkan dari $200 agar bisa jual)
                        if liquidity < 2000:
                            skipped_liquidity += 1
                            continue
                            
                        # FDV: Maksimal $500k (Cari koin micin potensial)
                        if fdv > 500_000:
                            skipped_fdv += 1
                            continue
                            
                    else:
                        # --- MODE TRADER (Updated: Alpha Hunter) ---
                        # Strategi: Cari Momentum & Uptrend
                        
                        # 1. Anti Bayi Prematur: Umur minimal 30 Menit
                        if pair_age_minutes < 30.0:
                            skipped_age += 1
                            continue
                            
                        # 2. Anti Rugpull: Likuiditas Minimal $5,000
                        if liquidity < 5000:
                            skipped_liquidity += 1
                            continue
                            
                        # 3. Anti Koin Sepi: Volume 1 Jam minimal $5,000
                        if volume_h1 < 5000:
                            skipped_volume += 1
                            continue
                            
                        # 4. WAJIB UPTREND: Harga 1 jam terakhir harus NAIK (> 0%)
                        if price_change_h1 <= 0:
                            skipped_trend += 1
                            continue

                    # Jika lolos semua filter, masukkan kandidat
                    candidates.append({
                        "symbol": symbol,
                        "address": address,
                        "pair_address": pair_address,
                        "liquidity": liquidity,
                        "volume_h1": volume_h1, # Kita pakai volume H1 buat sorting Trader
                        "volume": volume_24h,
                        "fdv": fdv,
                        "price_change_h1": price_change_h1,
                        "age_minutes": pair_age_minutes,
                        "age_hours": pair_age_hours,
                        "url": p.get('url')
                    })
                
                # === LANGKAH 5: SORTING & SELECTION ===
                if candidates:
                    if mode == "SNIPER":
                        # Sniper: Prioritas Likuiditas Tertinggi (Cari yang paling siap di antara yang baru)
                        candidates.sort(key=lambda x: x['liquidity'], reverse=True)
                    else:
                        # Trader: Prioritas Volume H1 Tertinggi (Cari yang sedang HYPE)
                        candidates.sort(key=lambda x: x['volume_h1'], reverse=True)
                        
                    best_gem = candidates[0]
                    
                    age_label = f"{best_gem['age_minutes']:.1f}m" if best_gem['age_minutes'] < 60 else f"{best_gem['age_hours']:.2f}h"
                    trend_emoji = "NZ" if best_gem.get('price_change_h1', 0) > 0 else "🔻"
                    
                    sys_logger.add_log(
                        f"💎 GEM ({mode}): {best_gem['symbol']} | Age: {age_label} | "
                        f"Liq: ${best_gem['liquidity']:,.0f} | Vol(1h): ${best_gem['volume_h1']:,.0f} | "
                        f"Trend: {best_gem.get('price_change_h1')}% {trend_emoji}"
                    )
                    return best_gem
                
                # Log detail kenapa kosong (Untuk Debugging)
                sys_logger.add_log(
                    f"⚠️ No Result ({mode}). Skip: Quote={skipped_quote}, Age={skipped_age}, FDV={skipped_fdv}, "
                    f"Stable={skipped_stable}, Liq={skipped_liquidity}, Vol={skipped_volume}, "
                    f"Trend={skipped_trend}, Ignored={skipped_ignore}"
                )
                return None

        except Exception as e:
            sys_logger.add_log(f"❌ Scanner Error: {e}")
            return None

scanner = SolanaScanner()
