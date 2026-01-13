# scripts/load_candles.py

import asyncio
import aiohttp
import pandas as pd
import argparse
import sys
from pathlib import Path

# =============================
# CONFIG
# =============================
GECKO_BASE = "https://api.geckoterminal.com/api/v2"
NETWORK = "solana"
INTERVAL = "minute"   # minute | hour | day
LIMIT_MAX = 1000      # Gecko limit

# =============================
# FETCH FUNCTION
# =============================
async def fetch_candles(pool_id: str, limit: int) -> pd.DataFrame | None:
    url = (
        f"{GECKO_BASE}/networks/{NETWORK}/pools/"
        f"{pool_id}/ohlcv/{INTERVAL}"
        f"?limit={limit}"
    )

    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=15) as resp:
            if resp.status != 200:
                print(f"❌ HTTP ERROR {resp.status}")
                try:
                    print(await resp.text())
                except Exception:
                    pass
                return None

            data = await resp.json()

    if "data" not in data:
        print("❌ INVALID RESPONSE")
        return None

    attrs = data["data"].get("attributes")
    rows = attrs.get("ohlcv_list") if attrs else None
    if not rows:
        print("❌ EMPTY CANDLE DATA")
        return None

    df = pd.DataFrame(
        rows,
        columns=["ts", "open", "high", "low", "close", "volume"]
    )

    df["ts"] = pd.to_datetime(df["ts"], unit="s")
    df.sort_values("ts", inplace=True)
    df.reset_index(drop=True, inplace=True)

    return df

# =============================
# MAIN
# =============================
async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool", required=True, help="GeckoTerminal pool id")
    parser.add_argument("--out", default="data/candles", help="Output directory")
    parser.add_argument("--minutes", type=int, default=500)
    args = parser.parse_args()

    limit = min(args.minutes, LIMIT_MAX)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    print("📡 Fetching candles from GeckoTerminal...")
    print(f"• Pool ID : {args.pool}")
    print(f"• Limit   : {limit}")

    df = await fetch_candles(args.pool, limit)

    if df is None:
        print("❌ Failed to load candles")
        sys.exit(1)

    out_file = out_dir / f"{args.pool}.csv"
    df.to_csv(out_file, index=False)

    print("✅ SUCCESS")
    print(f"• Candles : {len(df)} rows")
    print(f"• Saved   : {out_file}")

if __name__ == "__main__":
    asyncio.run(main())
