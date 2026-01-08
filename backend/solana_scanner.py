# File: backend/solana_scanner.py
import aiohttp
import asyncio
import sys_logger 

# KEMBALI KE METODE SEARCH (Lebih variatif daripada cari Token Address)
DEX_API = "https://api.dexscreener.com/latest/dex/search?q=SOL"
WSOL_ADDRESS = "So11111111111111111111111111111111111111112"

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
                    # Debug: Hitung berapa yang discan
                    skipped_stable = 0
                    skipped_ignore = 0
                    
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
                        
                        if liquidity > 100 and volume_24h > 100:
                            candidates.append({
                                "symbol": symbol,
                                "address": address,
                                "liquidity": liquidity,
                                "volume": volume_24h,
                                "url": p['url']
                            })

                    if candidates:
                        # Pilih Volume Tertinggi
                        candidates.sort(key=lambda x: x['volume'], reverse=True)
                        best_gem = candidates[0]
                        sys_logger.add_log(f"💎 GEM: {best_gem['symbol']} | Vol: ${best_gem['volume']:,.0f}")
                        return best_gem
                    
                    # Log detail kenapa kosong
                    sys_logger.add_log(f"⚠️ No Result. Stable: {skipped_stable}, Ignored: {skipped_ignore}")
                    return None

        except Exception as e:
            sys_logger.add_log(f"❌ Scanner Error: {e}")
            return None

scanner = SolanaScanner()