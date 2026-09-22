from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest

from bot.config import Config
from bot.main import VideoBot
from bot.providers import Video
from bot.store import Subscription


def client():
    return VideoBot(Config("test-only", 123, "ru", 120, 5, True, 5, 60, Path("missing.png"), True))


async def test_delivery_and_disabled_mentions():
    bot = client()
    channel = MagicMock(spec=discord.TextChannel)
    channel.permissions_for.return_value = NS(view_channel=True, send_messages=True, embed_links=True)
    channel.send = AsyncMock()
    guild = MagicMock()
    guild.get_channel.return_value = channel
    bot.guild = lambda: guild
    await bot.send_video(Subscription(1, "rss", "https://example.org/feed", 123),
                         Video("1", "@everyone " + "a" * 300, "https://example.org/video"))
    kwargs = channel.send.call_args.kwargs
    assert len(kwargs["embed"].title) == 256
    assert kwargs["allowed_mentions"].to_dict() == {"parse": []}
    assert kwargs["content"] == "https://example.org/video"


async def test_missing_channel_permission_does_not_send():
    bot = client()
    channel = MagicMock(spec=discord.TextChannel)
    channel.permissions_for.return_value = NS(view_channel=True, send_messages=False, embed_links=True)
    channel.send = AsyncMock()
    guild = MagicMock()
    guild.get_channel.return_value = channel
    bot.guild = lambda: guild
    with pytest.raises(ValueError, match="permissions"):
        await bot.send_video(Subscription(1, "rss", "https://example.org/feed", 123),
                             Video("1", "Video", "https://example.org/video"))
    channel.send.assert_not_awaited()


async def test_missing_server_capability_disables_banner_only():
    bot = client()
    guild = MagicMock()
    guild.features = []
    guild.edit = AsyncMock()
    bot.guild = lambda: guild
    await bot.banner_loop.coro(bot)
    assert bot.banner_blocked
    guild.edit.assert_not_awaited()
    assert len(bot.tree.get_commands(guild=bot.scope)) == 6
