"""Local account aliases; credentials never travel through Discord commands or SQLite."""
import json
import math
import os
import re
import time


class Accounts:
    def __init__(self, path):
        self.path = path

    def get(self, platform, alias):
        if platform not in {"tiktok", "instagram", "vimeo"}:
            raise ValueError("Unsupported account platform")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            account = data[alias]
        except (OSError, ValueError, KeyError, TypeError):
            raise ValueError("Configure this account alias in accounts.json; see docs/platforms.md") from None
        if not isinstance(account, dict) or account.get("platform") != platform:
            raise ValueError("Account alias has the wrong platform")
        env_name = account.get("token_env", "")
        if not isinstance(env_name, str) or not re.fullmatch(r"[A-Z][A-Z0-9_]+", env_name):
            raise ValueError("Configure token_env as the environment variable name, not the token")
        token = os.getenv(env_name, "").strip()
        if not token:
            raise ValueError("Account token is missing; set its token_env variable and restart")
        if any(char.isspace() for char in token):
            raise ValueError("Account token contains invalid whitespace")
        if account.get("expires_at") is not None:
            try:
                expires = float(account["expires_at"])
                if not math.isfinite(expires):
                    raise ValueError
            except (ValueError, TypeError):
                raise ValueError("expires_at must be a finite Unix timestamp") from None
            if expires <= time.time():
                raise ValueError("Account token expired; renew authorization and restart")
        if platform in {"instagram", "vimeo"} and not re.fullmatch(r"[0-9]+", str(account.get("user_id", ""))):
            raise ValueError("Set a real numeric user_id for this account")
        if platform == "instagram" and not re.fullmatch(r"v[0-9]+\.0", account.get("api_version", "")):
            raise ValueError("Set the supported Graph API version from your Meta app dashboard")
        return account, {"Authorization": f"Bearer {token}"}
