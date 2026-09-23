import asyncio
import calendar
import ipaddress
import json
import math
import os
import re
import socket
import time
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from urllib.parse import unquote, urlsplit

import aiohttp
import feedparser

MAX_BODY = 2 * 1024 * 1024
PLATFORMS = ("youtube", "twitch", "tiktok", "instagram", "vimeo", "peertube", "rss")


class UpstreamError(ValueError):
    def __init__(self, status, retry_after=0):
        self.status = status
        self.retry_after = retry_after
        super().__init__(f"Upstream HTTP {status}")


def retry_delay(headers, now):
    delays = [0.0]
    value = headers.get("Retry-After", "0")
    try:
        delays.append(float(value))
    except (ValueError, TypeError):
        try:
            delays.append(parsedate_to_datetime(value).timestamp() - now)
        except (ValueError, TypeError, OverflowError):
            pass
    try:
        delays.append(float(headers.get("Ratelimit-Reset", "0")) - now)
    except (ValueError, TypeError):
        pass
    return min(86400, max(delay for delay in delays if math.isfinite(delay)))


def timestamp(value):
    if not value:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return datetime.fromisoformat(value).timestamp()


@dataclass(frozen=True)
class Video:
    id: str
    title: str
    url: str
    published_at: float | None = None


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
        if source.startswith("https://"):
            public_url(source)
            parts = urlsplit(source)
            if parts.hostname not in {"youtube.com", "www.youtube.com"}:
                raise ValueError("Use a youtube.com channel URL")
            source = unquote(parts.path).strip("/")
            source = source.removeprefix("channel/")
            for tab in ("/videos", "/shorts", "/streams", "/featured"):
                source = source.removesuffix(tab)
        if not re.fullmatch(r"UC[A-Za-z0-9_-]{22}|@[\w.\-]{1,30}", source):
            raise ValueError("YouTube needs a UC channel ID or @handle / channel URL")
    elif kind == "twitch":
        source = source.removeprefix("https://www.twitch.tv/").removeprefix("https://twitch.tv/")
        source = source.rstrip("/").lower()
        if not re.fullmatch(r"[a-z0-9_]{1,25}", source):
            raise ValueError("Twitch needs a channel login")
    elif kind == "rss":
        public_url(source)
    elif kind in {"tiktok", "instagram", "vimeo"}:
        if not re.fullmatch(r"[a-z0-9_-]{1,48}", source):
            raise ValueError("Use an account alias from accounts.json, never an access token")
    elif kind == "peertube":
        public_url(source)
        parts = urlsplit(source)
        if parts.query or parts.fragment or not re.fullmatch(r"/c/[\w.@-]+/?|/video-channels/[\w.@-]+/?", parts.path):
            raise ValueError("Use https://instance/c/channel or /video-channels/channel")
        handle = parts.path.rstrip("/").rsplit("/", 1)[1]
        source = f"https://{parts.netloc.lower()}/video-channels/{handle}"
    else:
        raise ValueError("Unsupported provider")
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
        published = entry.get("published_parsed")
        result.append(Video(str(entry.get("id") or url), str(entry.get("title") or "Video"), url,
                            calendar.timegm(published) if published else None))
    if parsed.entries and not result:
        raise ValueError("Feed contains no usable public HTTPS links")
    # Most RSS/Atom feeds and YouTube return newest first.
    return list(reversed(result))


class Providers:
    def __init__(self, session, accounts=None, max_pages=3):
        self.session = session
        self.token = None
        self.expires = 0
        self.accounts = accounts
        self.max_pages = max_pages
        self.windows = {}  # Sources whose latest fetch reached the configured page limit.

    async def json(self, method, url, **kwargs):
        return json.loads(await self.request(method, url, **kwargs))

    async def resolve(self, kind, source):
        source = normalize(kind, source)
        if kind == "youtube" and source.startswith("@"):
            key = os.getenv("YOUTUBE_API_KEY", "")
            if not key:
                raise ValueError("Set YOUTUBE_API_KEY to resolve @handles, or use the UC channel ID")
            data = await self.json("GET", "https://www.googleapis.com/youtube/v3/channels",
                                   params={"part": "id", "forHandle": source, "key": key})
            if not data.get("items"):
                raise ValueError("YouTube channel not found")
            return normalize("youtube", data["items"][0]["id"])
        return source

    async def request(self, method, url, **kwargs):
        public_url(url)
        # Redirects are disabled: no redirect to internal endpoints or credential forwarding.
        async with self.session.request(method, url, allow_redirects=False, **kwargs) as response:
            if response.status != 200:
                raise UpstreamError(response.status, retry_delay(response.headers, time.time()))
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
        if kind not in PLATFORMS:
            raise ValueError("Unsupported provider")
        self.windows[(kind, source)] = False
        if kind in {"tiktok", "instagram", "vimeo", "peertube"}:
            from .adapters import fetch_extended
            return await fetch_extended(self, kind, source)
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
            videos = []
            cursor = None
            for _ in range(self.max_pages):
                params = {"user_id": user["data"][0]["id"], "first": 100, "sort": "time"}
                if cursor:
                    params["after"] = cursor
                data = await self.json("GET", "https://api.twitch.tv/helix/videos", headers=headers, params=params)
                videos.extend(Video(v["id"], v["title"], public_url(v["url"]), timestamp(v.get("published_at")))
                              for v in data["data"])
                cursor = data.get("pagination", {}).get("cursor")
                if not cursor:
                    break
            self.windows[(kind, source)] = bool(cursor)
        except UpstreamError as exc:
            if exc.status == 401:
                self.expires = 0
            raise
        return list(reversed(videos))
