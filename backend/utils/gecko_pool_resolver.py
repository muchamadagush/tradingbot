import requests

GECKO_API = "https://api.geckoterminal.com/api/v2"

def resolve_best_pool(token_address: str) -> str | None:
    """
    Resolve BEST GeckoTerminal pool_id for a Solana token
    Returns pool_id or None
    """
    url = f"{GECKO_API}/networks/solana/tokens/{token_address}/pools"

    try:
        r = requests.get(url, timeout=10)
        if r.status_code != 200:
            print("❌ Gecko error:", r.text)
            return None

        data = r.json()
        pools = data.get("data", [])

        if not pools:
            return None

        # Sort by liquidity desc
        pools.sort(
            key=lambda p: float(
                p["attributes"].get("reserve_in_usd", 0)
            ),
            reverse=True
        )

        best = pools[0]
        return best["id"]

    except Exception as e:
        print("❌ Resolver exception:", e)
        return None
