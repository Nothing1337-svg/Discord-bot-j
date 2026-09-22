import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent


def number(name, default, minimum=1):
    value = int(os.getenv(name, str(default)))
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value


def boolean(name, default=False):
    value = os.getenv(name, str(default)).lower()
    if value not in {"true", "false"}:
        raise ValueError(f"{name}: use true or false")
    return value == "true"


@dataclass(frozen=True)
class Config:
    token: str
    guild_id: int
    language: str
    poll_seconds: int
    max_send: int
    banner_enabled: bool
    debounce: int
    cooldown: int
    background: Path
    exclude_afk: bool
    api_max_pages: int = 3

    @classmethod
    def load(cls):
        load_dotenv(ROOT / ".env")
        token = os.getenv("DISCORD_TOKEN", "").strip()
        if not token:
            raise ValueError("Set DISCORD_TOKEN in .env")
        language = os.getenv("LANGUAGE", "ru")
        if language not in {"ru", "en"}:
            raise ValueError("LANGUAGE must be ru or en")
        pages = number("API_MAX_PAGES", 3)
        if pages > 10:
            raise ValueError("API_MAX_PAGES must be between 1 and 10")
        return cls(token, number("GUILD_ID", 0), language, number("POLL_SECONDS", 120, 30),
                   number("MAX_SEND_PER_POLL", 5), boolean("BANNER_ENABLED"),
                   number("BANNER_DEBOUNCE_SECONDS", 5), number("BANNER_COOLDOWN_SECONDS", 60, 30),
                   ROOT / os.getenv("BACKGROUND", "assets/background.png"), boolean("EXCLUDE_AFK", True), pages)
