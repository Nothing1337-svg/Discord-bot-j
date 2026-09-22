"""Offline preflight. Prints names of missing settings, never credential values."""
import json
import os
import sys

from dotenv import load_dotenv

from .accounts import Accounts
from .config import ROOT, Config


def check():
    load_dotenv(ROOT / ".env")
    errors = []
    for name in ("DISCORD_TOKEN", "GUILD_ID"):
        if not os.getenv(name, "").strip():
            errors.append(f"Missing {name}")
    if not errors:
        try:
            Config.load()
        except ValueError:
            errors.append("Invalid .env configuration; check numeric settings, booleans and LANGUAGE")
    path = ROOT / os.getenv("ACCOUNTS_FILE", "accounts.json")
    if path.exists():
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            for alias, account in data.items():
                # Example aliases must be removed or configured before enabling them.
                Accounts(path).get(account["platform"], alias)
        except (OSError, ValueError, KeyError, TypeError, AttributeError):
            errors.append("accounts.json has unconfigured/expired entries; fill or remove unused accounts")
    for message in errors:
        print(message)
    if not errors:
        print("Local settings validated. Discord login, permissions and platform API access are NOT verified.")
    else:
        print("Preflight incomplete. No network requests or Discord messages were sent.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(check())
