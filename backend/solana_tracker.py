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
    """Menyimpan transaksi baru"""
    history = load_history()
    
    trade = {
        "id": f"SOL-{int(time.time())}", # ID Unik
        "timestamp": datetime.now().isoformat(),
        "symbol": f"{output_token}/{input_token}", # Format: BONK/SOL
        "side": "BUY",
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