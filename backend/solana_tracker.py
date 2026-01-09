# File: backend/solana_tracker.py
import json
import os
import time
from datetime import datetime

FILE_PATH = "solana_trades.json"

def load_history():
    """Membaca riwayat dari file JSON"""
    if not os.path.exists(FILE_PATH):
        return []
    try:
        with open(FILE_PATH, "r") as f:
            return json.load(f)
    except:
        return []

def save_trade(txid, input_token, output_token, input_amount, output_estimate, status="Success"):
    """Menyimpan transaksi baru dengan deteksi BUY/SELL yang akurat"""
    history = load_history()
    
    # --- LOGIKA DETEKSI SIDE (BUY/SELL) ---
    # Jika input adalah SOL/WSOL, berarti kita membeli token lain (BUY)
    # Jika input adalah token lain, berarti kita menjual ke SOL (SELL)
    is_buying = input_token in ["SOL", "WSOL"]
    side = "BUY" if is_buying else "SELL"
    
    # --- FORMAT SYMBOL KONSISTEN: SELALU TOKEN/SOL ---
    # Jika BUY: input=SOL, output=TOKEN → symbol = TOKEN/SOL
    # Jika SELL: input=TOKEN, output=SOL → symbol = TOKEN/SOL
    if is_buying:
        token_symbol = output_token  # Kita beli token ini
        symbol = f"{token_symbol}/SOL"
    else:
        token_symbol = input_token  # Kita jual token ini
        symbol = f"{token_symbol}/SOL"
    
    # --- LOG CONSOLE YANG JELAS ---
    print(f"\n{'='*60}")
    print(f"📝 Recording Transaction: {side}")
    print(f"   Symbol: {symbol}")
    print(f"   In:  {input_amount:.8f} {input_token}")
    print(f"   Out: {output_estimate:.8f} {output_token}")
    print(f"   Status: {status}")
    print(f"   TxID: {txid}")
    print(f"{'='*60}\n")
    
    trade = {
        "id": f"SOL-{int(time.time())}", # ID Unik
        "timestamp": datetime.now().isoformat(),
        "symbol": symbol,
        "side": side,
        "price": 0, # Kita hitung nanti di frontend
        "amount_in": input_amount,
        "amount_out": output_estimate,
        "txid": txid,
        "status": status,
        "source": "Jupiter"
    }
    
    # Simpan di paling atas (terbaru)
    history.insert(0, trade)
    
    # Batasi cuma simpan 50 transaksi terakhir
    if len(history) > 50:
        history = history[:50]
        
    with open(FILE_PATH, "w") as f:
        json.dump(history, f, indent=4)
        
    return trade