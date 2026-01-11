import aiohttp
import socket
import os
import base64
import json
import random
import string
from typing import Optional
from aiohttp.resolver import DefaultResolver
from dotenv import load_dotenv
import sys_logger

from solders.keypair import Keypair # type: ignore
from solders.transaction import VersionedTransaction # type: ignore
from solana.rpc.async_api import AsyncClient

load_dotenv()

# --- 1. DAFTAR TOKEN ---
TOKENS = {
    "SOL": "So11111111111111111111111111111111111111112",
    "USDC": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v", 
    "USDT": "Es9vMFrzaCERmJfrF4H2FYD4KCoNkY11McCe8BenwNYB", 
    "BONK": "DezXAZ8z7PnrnRJjz3wKhDlW5TGhPQW3Q5G6pH4Q4", 
    "WIF": "EKpQGSJtjMFqKZ9KQanSqYXRcF8fBopzLHYxdM65zcjm", 
    "RAY": "4k3Dyjzvzp8eMZWUXbBCjEvwSkkk59S5iCNLY3QrkX6R", 
    "JUP": "JUPyiwrYJFskUPiHa7hkeR8VUtAeFoSYbKedZNsDvCN", 
    "PYTH": "HZ1JovNiVvGrGNiiYvEozEVgZ58xaU3RKwX8eACQBCt3"
}

# Map balik dari Address ke Simbol (Untuk display saldo)
ADDRESS_TO_SYMBOL = {v: k for k, v in TOKENS.items()}

TARGET_HOST = "api.jup.ag"
# KEMBALI KE V1 (Sesuai Request)
QUOTE_URL = f"https://{TARGET_HOST}/swap/v1/quote"
SWAP_URL = f"https://{TARGET_HOST}/swap/v1/swap"

RPC_URL = os.getenv("SOLANA_RPC_URL", "https://api.mainnet-beta.solana.com")
PRIVATE_KEY = os.getenv("SOLANA_PRIVATE_KEY")
API_KEY = os.getenv("JUPITER_API_KEY")
IS_SIMULATION = os.getenv("IS_SIMULATION", "TRUE").upper() == "TRUE"

class MagicResolver(DefaultResolver):
    def __init__(self, override_ip):
        self.override_ip = override_ip
        super().__init__()
    async def resolve(self, host, port=0, family=socket.AF_INET):
        if host == TARGET_HOST and self.override_ip:
            return [{'hostname': host, 'host': self.override_ip, 'port': port, 'family': family, 'proto': 0, 'flags': 0}]
        return await super().resolve(host, port, family)

class JupiterManager:
    def __init__(self):
        self.rpc_client = AsyncClient(RPC_URL)
        try:
            if PRIVATE_KEY:
                self.payer = Keypair.from_base58_string(PRIVATE_KEY)
                mode_str = "👻 SIMULATION" if IS_SIMULATION else "💸 REAL MONEY"
                print(f"✅ Wallet: {self.payer.pubkey()} | {mode_str}")
            else:
                self.payer = None
        except Exception as e:
            print(f"❌ Wallet Error: {e}")
            self.payer = None

    async def _get_real_ip_via_google(self):
        try:
            connector = aiohttp.TCPConnector(ssl=False)
            async with aiohttp.ClientSession(connector=connector) as session:
                async with session.get(f"https://dns.google/resolve?name={TARGET_HOST}&type=A") as response:
                    data = await response.json()
                    if 'Answer' in data: return data['Answer'][0]['data']
        except: pass
        return "104.18.40.155"

    async def _get_session(self):
        real_ip = await self._get_real_ip_via_google()
        resolver = MagicResolver(override_ip=real_ip)
        connector = aiohttp.TCPConnector(resolver=resolver, family=socket.AF_INET, ssl=False)
        return aiohttp.ClientSession(connector=connector)

    async def get_token_balances(self):
        if not self.payer: return {"SOL": 0}
        
        balances = {}
        pubkey_str = str(self.payer.pubkey())
        payload = {
            "jsonrpc": "2.0", "id": 1, "method": "getTokenAccountsByOwner",
            "params": [
                pubkey_str,
                {"programId": "TokenkegQfeZyiNwAJbNbGKPFXCWuBvf9Ss623VQ5DA"},
                {"encoding": "jsonParsed"}
            ]
        }

        try:
            # 1. Ambil SOL
            sol_resp = await self.rpc_client.get_balance(self.payer.pubkey())
            balances["SOL"] = sol_resp.value / 1_000_000_000
            
            # 2. Ambil Token SPL
            async with aiohttp.ClientSession() as session:
                async with session.post(RPC_URL, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if 'result' in data and 'value' in data['result']:
                            items = data['result']['value']
                            for item in items:
                                try:
                                    info = item['account']['data']['parsed']['info']
                                    mint = info['mint']
                                    amount_ui = float(info['tokenAmount']['uiAmount'] or 0)
                                    if amount_ui > 0:
                                        symbol = ADDRESS_TO_SYMBOL.get(mint, None)
                                        if symbol:
                                            balances[symbol] = amount_ui
                                        else:
                                            balances[mint] = amount_ui
                                except: continue
        except Exception as e:
            print(f"❌ Balance Error: {e}")
            if "SOL" not in balances: balances["SOL"] = 0
            
            return balances
    
    async def get_quote(self, input_token="SOL", output_token="USDC", amount_sol=0.01, slippage_bps=50):
        try:
            # --- LOGIKA BARU: Cek Kamus Dulu, Kalau Tidak Ada Anggap Itu Address ---
            # Cek apakah input_token ada di kamus TOKENS, jika tidak, cek apakah panjang stringnya > 10 (asumsi address)
            input_mint = TOKENS.get(input_token)
            if not input_mint and len(input_token) > 10:
                input_mint = input_token
            
            output_mint = TOKENS.get(output_token)
            if not output_mint and len(output_token) > 10:
                output_mint = output_token
            # -----------------------------------------------------------------------

            if not input_mint: return {"error": f"Token {input_token} invalid/not found"}
            if not output_mint: return {"error": f"Token {output_token} invalid/not found"}

            # --- FIX DESIMAL ---
            input_decimals = 9
            if input_token != "SOL" and input_token != "WSOL":
                input_decimals = 6 
                if input_token == "BONK": input_decimals = 5
                if input_token == "USDC" or input_token == "USDT": input_decimals = 6
            
            amount_lamport = int(float(amount_sol) * (10 ** input_decimals))
            
            effective_slippage = slippage_bps
            if effective_slippage is None:
                # Default ke env jika tersedia, fallback 50 bps (0.5%)
                try:
                    effective_slippage = int(os.getenv("JUPITER_DEFAULT_SLIPPAGE_BPS", "50"))
                except:  # pragma: no cover - fallback aman
                    effective_slippage = 50

            params = {
                "inputMint": input_mint, 
                "outputMint": output_mint, 
                "amount": str(amount_lamport), 
                "slippageBps": str(effective_slippage)
            }
            headers = {"x-api-key": API_KEY} if API_KEY else {}

            session = await self._get_session()
            async with session:
                async with session.get(QUOTE_URL, params=params, headers=headers) as response:
                    data = await response.json()
                    
                    # --- SMART PARSING V1/V6 ---
                    # V1 seringkali membungkus response dalam "data" atau "routePlan"
                    # Kita cari 'outAmount' dimanapun dia berada
                    quote_data = data
                    if "data" in data and isinstance(data["data"], dict):
                        quote_data = data["data"]
                    elif "routePlan" in data: # Struktur lain
                        # Jika format sangat beda, kita ambil info dasar saja jika ada
                        pass

                    if "outAmount" not in quote_data:
                         return {"error": f"Jupiter: {data.get('error', 'Unknown Error/Format V1')}"}
                    
                    out_decimals = 6
                    if output_token == "SOL": out_decimals = 9
                    if output_token == "BONK": out_decimals = 5
                    
                    out_raw = int(quote_data['outAmount'])
                    return {
                        "status": "success", 
                        "output_estimate": f"{(out_raw/(10**out_decimals)):,.6f}", 
                        "raw_data": quote_data # Return data bersih
                    }
        except Exception as e:
            return {"error": str(e)}

    async def execute_swap(self, quote_response):
        if not self.payer: return {"error": "Private Key missing"}
        if IS_SIMULATION:
            return {"status": "success", "txid": f"SIMULATED_{''.join(random.choices(string.ascii_letters, k=8))}", "message": "Simulasi Berhasil"}
        
        # --- PANIC SELL RETRY LOGIC ---
        async def _try_swap(quote_json):
            try:
                # Payload V1 mungkin beda sedikit, tapi field ini standar
                payload = {
                    "userPublicKey": str(self.payer.pubkey()),
                    "quoteResponse": quote_json,
                    # Hapus parameter V6 jika pakai V1 agar tidak error
                    # "dynamicComputeUnitLimit": True,   
                    # "prioritizationFeeLamports": "auto" 
                }
                headers = {"x-api-key": API_KEY, "Content-Type": "application/json"}
                
                session = await self._get_session()
                async with session:
                    async with session.post(SWAP_URL, json=payload, headers=headers) as response:
                        swap_data = await response.json()
                
                if "swapTransaction" not in swap_data:
                    return {"error": f"Swap Error: {swap_data}"}
                
                raw_tx = base64.b64decode(swap_data['swapTransaction'])
                txn = VersionedTransaction.from_bytes(raw_tx)
                signature = self.payer.sign_message(txn.message.to_bytes_versioned(txn.message))
                signed_txn = VersionedTransaction.populate(txn.message, [signature])
                
                opts = await self.rpc_client.send_raw_transaction(bytes(signed_txn))
                return {"status": "success", "txid": str(opts.value), "explorer_url": f"https://solscan.io/tx/{str(opts.value)}"}
            except Exception as e:
                return {"error": str(e)}

        # Percobaan 1
        result = await _try_swap(quote_response)
        if result.get("status") == "success":
            return result

        # --- RETRY MODE ---
        sys_logger.add_log(f"⚠️ Swap 1 gagal: {result.get('error')}. Memulai Panic Retry...")
        
        try:
            # Parsing Safe untuk Retry
            qr = quote_response
            input_mint = qr.get("inputMint")
            output_mint = qr.get("outputMint")
            in_amount_raw = int(qr.get("inAmount"))
            
            in_decimals = 9 if input_mint == TOKENS["SOL"] else 6
            if input_mint == TOKENS["BONK"]: in_decimals = 5
            
            amount_ui = in_amount_raw / (10 ** in_decimals)
            
            input_symbol = ADDRESS_TO_SYMBOL.get(input_mint, input_mint)
            output_symbol = ADDRESS_TO_SYMBOL.get(output_mint, output_mint)

        except Exception as e:
            sys_logger.add_log(f"❌ Gagal prepare retry: {e}")
            return result 

        # Loop Retry Slippage
        for slippage in [500, 1000]: 
            sys_logger.add_log(f"🔄 Retrying with {slippage/100}% Slippage...")
            
            new_quote = await self.get_quote(input_symbol, output_symbol, amount_ui, slippage_bps=slippage)
            if "error" in new_quote:
                sys_logger.add_log(f"❌ Re-quote fail: {new_quote['error']}")
                continue
                
            result_retry = await _try_swap(new_quote["raw_data"])
            if result_retry.get("status") == "success":
                sys_logger.add_log(f"✅ Panic Retry Success!")
                return result_retry

        return result

jupiter_bot = JupiterManager()