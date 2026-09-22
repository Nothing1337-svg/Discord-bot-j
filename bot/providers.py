import asyncio
import ipaddress
import json
import os
import re
import socket
import time
from dataclasses import dataclass
from urllib.parse import urlsplit

import aiohttp
import feedparser

MAX_BODY = 2 * 1024 * 1024


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    url: str


def public_url(url):
    if len(url) > 2000 or any(char.isspace() or ord(char) < 32 for char in url):
        raise ValueError("URL must fit Discord's 2000-character limit and contain no whitespace")
    parts = urlsplit(url)
    if parts.scheme != "https" or not parts.hostname or parts.username or parts.password:
        raise ValueError("Use a public HTTPS URL without credentials")
    if parts.port not in (None, 443):
        raise ValueError("Only HTTPS port 443 is supported")
    try:
        address = ipaddress.ip_address(parts.hostname)
    except ValueError:
        if parts.hostname.lower() == "localhost" or parts.hostname.lower().endswith(".local"):
            raise ValueError("Local addresses are not allowed") from None
    else:
        if not address.is_global:
            raise ValueError("Private addresses are not allowed")
    return url


class PublicResolver(aiohttp.resolver.DefaultResolver):
    async def resolve(self, host, port=0, family=socket.AF_INET):
        results = await super().resolve(host, port, family)
        if any(not ipaddress.ip_address(r["host"]).is_global for r in results):
            raise ValueError("DNS resolved to a non-public address")
        return results


def normalize(kind, source):
    source = source.strip()
    if kind == "youtube":
        source = source.removeprefix("https://www.youtube.com/channel/").removeprefix(
            "https://youtube.com/channel/").rstrip("/")
        if not re.fullmatch(r"UC[\w-]{22}", source, flags=re.ASCII):
            raise ValueError("YouTube needs a UC channel ID (24 characters), not @handle")
    elif kind == "twitch":
        source = source.removeprefix("https://www.twitch.tv/").removeprefix("https://twitch.tv/")
        source = source.rstrip("/").lower()
        if not re.fullmatch(r"[a-z0-9_]{1,25}", source):
            raise ValueError("Twitch needs a channel login")
    elif kind == "rss":
        public_url(source)
    else:
        raise ValueError("Supported providers: youtube, twitch, rss")
    return source


def parse_feed(body):
    parsed = feedparser.parse(body)
    if parsed.bozo or not parsed.version:
        raise ValueError("Invalid RSS/Atom feed")
    result = []
    for entry in parsed.entries:
        url = entry.get("link", "")
        try:
            public_url(url)
        except ValueError:
            continue
        result.append(Video(str(entry.get("id", url)), str(entry.get("title", "Video")), url))
    if parsed.entries and not result:
        raise ValueError("Feed contains no usable public HTTPS links")
    # Most RSS/Atom feeds and YouTube return newest first.
    return list(reversed(result))


class Providers:
    def __init__(self, session):
        self.session = session
        self.token = None
        self.expires = 0

    async def request(self, method, url, **kwargs):
        public_url(url)
        # Redirects are disabled: no redirect to internal endpoints or credential forwarding.
        async with self.session.request(method, url, allow_redirects=False, **kwargs) as response:
            if response.status != 200:
                raise ValueError(f"Upstream HTTP {response.status}")
            body = bytearray()
            async for chunk in response.content.iter_chunked(65536):
                body.extend(chunk)
                if len(body) > MAX_BODY:
                    raise ValueError("Upstream body exceeds 2 MiB")
            return bytes(body)

    async def twitch_headers(self):
        client_id = os.getenv("TWITCH_CLIENT_ID", "")
        secret = os.getenv("TWITCH_CLIENT_SECRET", "")
        if not client_id or not secret:
            raise ValueError("Set TWITCH_CLIENT_ID and TWITCH_CLIENT_SECRET")
        if time.monotonic() >= self.expires:
            data = json.loads(await self.request("POST", "https://id.twitch.tv/oauth2/token", data={
                "client_id": client_id, "client_secret": secret, "grant_type": "client_credentials"}))
            self.token = data["access_token"]
            self.expires = time.monotonic() + max(0, data["expires_in"] - 60)
        return {"Client-ID": client_id, "Authorization": f"Bearer {self.token}"}

    async def fetch(self, kind, source):
        if kind not in {"youtube", "rss", "twitch"}:
            raise ValueError("Unsupported provider")
        if kind in {"youtube", "rss"}:
            url = f"https://www.youtube.com/feeds/videos.xml?channel_id={source}" if kind == "youtube" else source
            body = await self.request("GET", url)
            return await asyncio.to_thread(parse_feed, body)
        headers = await self.twitch_headers()
        try:
            user = json.loads(await self.request("GET", "https://api.twitch.tv/helix/users",
                                                 params={"login": source}, headers=headers))
            if not user["data"]:
                raise ValueError("Twitch channel not found")
            data = json.loads(await self.request("GET", "https://api.twitch.tv/helix/videos", headers=headers,
                                                 params={"user_id": user["data"][0]["id"], "first": 100}))
        except ValueError:
            self.expires = 0
            raise
        return [Video(v["id"], v["title"], public_url(v["url"])) for v in reversed(data["data"])]
