import asyncio
import io
import logging
import os
import time
from typing import Literal

import aiohttp
import discord
from discord import app_commands
from discord.ext import tasks

from .accounts import Accounts
from .banner import render
from .config import ROOT, Config
from .i18n import tr
from .network import tls_context
from .notifications import Notifier
from .providers import PLATFORMS, Providers, PublicResolver
from .store import Store
from .voice import BannerSchedule, voice_count

log = logging.getLogger(__name__)


class VideoBot(discord.Client):
    def __init__(self, config, connector=None):
        intents = discord.Intents.none()
        intents.guilds = True
        intents.voice_states = True
        super().__init__(intents=intents, allowed_mentions=discord.AllowedMentions.none(), connector=connector)
        self.config = config
        self.tree = app_commands.CommandTree(self)
        self.scope = discord.Object(id=config.guild_id)
        self.schedule = BannerSchedule(config.debounce, config.cooldown)
        self.banner_blocked = False
        self.register_commands()

    def text(self, key):
        return tr(self.config.language, key)

    async def setup_hook(self):
        (ROOT / "data").mkdir(exist_ok=True)
        self.store = Store(ROOT / "data" / "bot.sqlite3")
        self.session = aiohttp.ClientSession(
            connector=aiohttp.TCPConnector(resolver=PublicResolver(), ssl=tls_context()),
            timeout=aiohttp.ClientTimeout(total=25), headers={"User-Agent": "Discord-bot-j/1.0"})
        self.providers = Providers(self.session, Accounts(ROOT / os.getenv("ACCOUNTS_FILE", "accounts.json")),
                                   self.config.api_max_pages)
        self.notifier = Notifier(self.store, self.providers, self.send_video,
                                 self.config.max_send, self.config.poll_seconds)
        await self.tree.sync(guild=self.scope)
        self.poll_loop.change_interval(seconds=self.config.poll_seconds)
        self.poll_loop.start()
        if self.config.banner_enabled:
            self.banner_loop.start()

    async def close(self):
        running = [loop.get_task() for loop in (self.poll_loop, self.banner_loop) if loop.is_running()]
        self.poll_loop.cancel()
        self.banner_loop.cancel()
        if running:
            await asyncio.gather(*running, return_exceptions=True)
        if hasattr(self, "session"):
            await self.session.close()
        if hasattr(self, "store"):
            self.store.close()
        await super().close()

    def guild(self):
        return self.get_guild(self.config.guild_id)

    async def on_ready(self):
        guild = self.guild()
        if guild is None:
            log.error("Configured GUILD_ID unavailable. Invite bot to that server.")
            return
        log.info("Connected. Subscriptions: %s", len(self.store.all()))
        self.schedule.observe(voice_count(guild, self.config.exclude_afk))

    async def on_voice_state_update(self, member, before, after):
        if member.guild.id == self.config.guild_id:
            self.schedule.observe(voice_count(member.guild, self.config.exclude_afk))

    async def send_video(self, sub, video):
        guild = self.guild()
        channel = guild.get_channel(sub.channel_id) if guild else None
        if not isinstance(channel, discord.TextChannel):
            raise TypeError("Destination channel is unavailable")
        permissions = channel.permissions_for(guild.me)
        if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
            raise ValueError("Missing channel permissions")
        embed = discord.Embed(title=video.title[:256], url=video.url, color=0x54E5B1)
        embed.set_author(name=self.text("new"))
        embed.set_footer(text=sub.kind)
        await channel.send(content=video.url, embed=embed, allowed_mentions=discord.AllowedMentions.none())

    @tasks.loop(seconds=120)
    async def poll_loop(self):
        await self.notifier.poll()

    @poll_loop.before_loop
    async def before_poll(self):
        await self.wait_until_ready()

    @tasks.loop(seconds=1)
    async def banner_loop(self):
        guild = self.guild()
        if not guild or guild.unavailable or not guild.me or self.banner_blocked:
            return
        if "BANNER" not in guild.features or not guild.me.guild_permissions.manage_guild:
            log.warning("Banner disabled: BANNER feature and Manage Server are required. Restart after fixing.")
            self.banner_blocked = True
            return
        self.schedule.observe(voice_count(guild, self.config.exclude_afk))
        if not self.schedule.due():
            return
        value = self.schedule.value
        self.schedule.attempted()
        try:
            image = await asyncio.to_thread(render, value, self.config.language, self.config.background)
            await guild.edit(banner=image, reason="Voice online counter")
            self.schedule.success(value)
        except discord.Forbidden:
            self.banner_blocked = True
            log.warning("Banner forbidden; restart after fixing server permissions")
        except Exception as exc:  # noqa: BLE001 - keep worker alive; redact exception payloads
            log.warning("Banner update failed (%s); retry after cooldown", type(exc).__name__)

    @banner_loop.before_loop
    async def before_banner(self):
        await self.wait_until_ready()

    def register_commands(self):
        def admin_command(name, description):
            def decorate(func):
                func = app_commands.checks.has_permissions(manage_guild=True)(func)
                func = app_commands.default_permissions(manage_guild=True)(func)
                return self.tree.command(name=name, description=description, guild=self.scope)(func)
            return decorate

        @admin_command("subscribe", "Subscribe to new videos · Подписаться на новые видео")
        async def subscribe(interaction: discord.Interaction,
                            platform: Literal["youtube", "twitch", "tiktok", "instagram", "vimeo", "peertube", "rss"],
                            source: str, channel: discord.TextChannel):
            await interaction.response.defer(ephemeral=True)
            if channel.guild.id != self.config.guild_id:
                raise ValueError("Wrong guild")
            permissions = channel.permissions_for(channel.guild.me)
            if not (permissions.view_channel and permissions.send_messages and permissions.embed_links):
                raise ValueError("Missing destination permissions")
            source = await self.providers.resolve(platform, source)
            async with self.notifier.lock:
                started_at = time.time()
                baseline = await self.providers.fetch(platform, source)
                self.store.add(platform, source, channel.id, baseline, created_at=started_at)
            await interaction.followup.send(self.text("added"), ephemeral=True)

        @admin_command("unsubscribe", "Remove subscription by ID · Удалить подписку")
        async def unsubscribe(interaction: discord.Interaction, subscription_id: int):
            await interaction.response.defer(ephemeral=True)
            async with self.notifier.lock:
                removed = self.store.remove(subscription_id)
                self.notifier.forget(subscription_id)
            await interaction.followup.send(self.text("removed" if removed else "missing"), ephemeral=True)

        @admin_command("subscriptions", "List subscriptions · Список подписок")
        async def subscriptions(interaction: discord.Interaction):
            rows = self.store.all()
            if not rows:
                await interaction.response.send_message(self.text("empty"), ephemeral=True)
                return
            # Attachment avoids Discord's message length limit and accidental markdown/mentions.
            content = "\n".join(f"{s.id}\t{s.kind}\t{s.source}\t{s.channel_id}" for s in rows)
            await interaction.response.send_message(file=discord.File(
                io.BytesIO(content.encode("utf-8")), filename="subscriptions.txt"), ephemeral=True)

        @admin_command("check", "Check sources now · Проверить источники")
        @app_commands.checks.cooldown(1, 30, key=lambda i: i.guild_id)
        async def check(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            # Background work can exceed the interaction token lifetime for many subscriptions.
            await interaction.followup.send(self.text("checking"), ephemeral=True)
            await self.notifier.poll()

        @admin_command("status", "Show bot status · Состояние бота")
        async def status(interaction: discord.Interaction):
            sources = self.store.all()
            limits = sum(bool(self.providers.windows.get((s.kind, s.source))) for s in sources)
            health = self.text("working") if self.poll_loop.is_running() else self.text("stopped")
            await interaction.response.send_message(
                f"{health}\n{self.text('sources')}: {len(sources)}\n"
                f"{self.text('failed')}: {len(self.notifier.failures)}\n"
                f"{self.text('pending')}: {self.store.pending_count()}\n"
                f"{self.text('window')}: {limits}\n"
                f"Voice: {voice_count(interaction.guild, self.config.exclude_afk)}\n"
                f"Banner: enabled={self.config.banner_enabled}, blocked={self.banner_blocked}", ephemeral=True)

        @admin_command("platforms", "Supported platforms and setup · Платформы и настройка")
        async def platforms(interaction: discord.Interaction):
            await interaction.response.send_message(
                ", ".join(PLATFORMS) + "\n" + self.text("platform_help"), ephemeral=True)

        @admin_command("banner_preview", "Preview voice banner · Предпросмотр баннера")
        async def preview(interaction: discord.Interaction):
            await interaction.response.defer(ephemeral=True)
            count = voice_count(interaction.guild, self.config.exclude_afk)
            image = await asyncio.to_thread(render, count, self.config.language, self.config.background)
            await interaction.followup.send(file=discord.File(io.BytesIO(image), filename="banner.png"),
                                             ephemeral=True)

        @self.tree.error
        async def command_error(interaction, error):
            original = getattr(error, "original", error)
            log.warning("Command failed (%s)", type(original).__name__)
            message = self.text("error")
            if isinstance(original, (ValueError, app_commands.CheckFailure)):
                message += " " + str(original)[:500]
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)


def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    config = Config.load()
    async def run():
        connector = aiohttp.TCPConnector(ssl=tls_context())
        async with VideoBot(config, connector=connector) as bot:
            await bot.start(config.token)

    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
