"""
CLI script to generate valid API keys for admin, trader, and readonly roles.
Usage:
    python generate_role_api_keys_cli.py
"""
import secrets

roles = ["admin", "trader", "readonly"]

if __name__ == "__main__":
    for role in roles:
        api_key = secrets.token_hex(32)
        print(f"{role} API key: {api_key}")
