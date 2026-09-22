from pathlib import Path

import pytest

from bot.config import Config, boolean, number
from bot.main import VideoBot


def test_config_requires_real_values(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "")
    with pytest.raises(ValueError, match="DISCORD_TOKEN"):
        Config.load()
    monkeypatch.setenv("DISCORD_TOKEN", "test-only")
    monkeypatch.setenv("GUILD_ID", "")
    with pytest.raises(ValueError):
        Config.load()


def test_invalid_settings(monkeypatch):
    monkeypatch.setenv("POLL_SECONDS", "0")
    with pytest.raises(ValueError):
        number("POLL_SECONDS", 120, 30)
    monkeypatch.setenv("BANNER_ENABLED", "maybe")
    with pytest.raises(ValueError):
        boolean("BANNER_ENABLED")


def test_intents_commands_and_permissions():
    config = Config("test-only", 123, "ru", 120, 5, False, 5, 60, Path("background.png"), True)
    client = VideoBot(config)
    assert client.intents.guilds and client.intents.voice_states
    assert not client.intents.members and not client.intents.message_content and not client.intents.presences
    commands = client.tree.get_commands(guild=client.scope)
    assert {c.name for c in commands} == {"subscribe", "unsubscribe", "subscriptions", "check", "status", "banner_preview"}
    assert all(c.default_permissions.manage_guild and c.checks for c in commands)
    assert not client.allowed_mentions.everyone
