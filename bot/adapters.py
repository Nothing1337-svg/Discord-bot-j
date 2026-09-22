"""Official, read-only video APIs. Bounded pagination, no scraping or arbitrary next URLs."""
from urllib.parse import quote, urlsplit

from .providers import Video, public_url, timestamp


def item(id, title, url, published):
    return Video(str(id), str(title or "Video"), public_url(url), timestamp(published))


async def fetch_extended(provider, kind, source):
    if kind == "peertube":
        return await peertube(provider, source)
    if provider.accounts is None:
        raise ValueError("Configure accounts.json for this platform")
    account, headers = provider.accounts.get(kind, source)
    if kind == "tiktok":
        return await tiktok(provider, source, headers)
    if kind == "instagram":
        return await instagram(provider, source, account, headers)
    return await vimeo(provider, source, account, headers)


async def tiktok(p, source, headers):
    videos, cursor, more = [], None, False
    for _ in range(p.max_pages):
        body = {"max_count": 20}
        if cursor is not None:
            body["cursor"] = cursor
        data = await p.json("POST", "https://open.tiktokapis.com/v2/video/list/", headers=headers,
                            params={"fields": "id,title,share_url,create_time"}, json=body)
        if data.get("error", {}).get("code") != "ok":
            raise ValueError("TikTok API rejected the request; check token and video.list scope")
        page = data["data"]
        videos.extend(item(v["id"], v.get("title"), v["share_url"], v["create_time"])
                      for v in page["videos"])
        more = page.get("has_more", False)
        if not more:
            break
        next_cursor = page.get("cursor")
        if next_cursor is None or next_cursor == cursor:
            raise ValueError("TikTok pagination did not advance")
        cursor = next_cursor
    p.windows[("tiktok", source)] = bool(more)
    return list(reversed(videos))


async def instagram(p, source, account, headers):
    url = f"https://graph.instagram.com/{account['api_version']}/{account['user_id']}/media"
    videos, cursor, more = [], None, False
    for _ in range(p.max_pages):
        params = {"fields": "id,caption,media_type,permalink,timestamp", "limit": 100}
        if cursor:
            params["after"] = cursor
        data = await p.json("GET", url, headers=headers, params=params)
        if "error" in data:
            raise ValueError("Instagram API rejected the request; check account authorization")
        # Single videos and Reels have media_type VIDEO. Photos/carousels/stories are not video alerts.
        videos.extend(item(v["id"], v.get("caption"), v["permalink"], v["timestamp"])
                      for v in data["data"] if v.get("media_type") == "VIDEO")
        paging = data.get("paging", {})
        more = bool(paging.get("next"))
        if not more:
            break
        next_cursor = paging.get("cursors", {}).get("after")
        if not next_cursor or next_cursor == cursor:
            raise ValueError("Instagram pagination did not advance")
        cursor = next_cursor  # Never follow paging.next: it may embed credentials or a different host.
    p.windows[("instagram", source)] = more
    return sorted(videos, key=lambda v: v.published_at)


async def vimeo(p, source, account, headers):
    videos, more = [], False
    for page in range(1, p.max_pages + 1):
        data = await p.json("GET", f"https://api.vimeo.com/users/{account['user_id']}/videos", headers=headers,
                            params={"sort": "date", "direction": "desc", "page": page, "per_page": 25})
        # Even an overprivileged token must never cause private/unlisted videos to be broadcast.
        videos.extend(item(v["uri"], v.get("name"), v["link"], v["created_time"])
                      for v in data["data"] if v.get("privacy", {}).get("view") == "anybody"
                      and v.get("status") == "available")
        more = bool(data.get("paging", {}).get("next"))
        if not more:
            break
    p.windows[("vimeo", source)] = more
    return list(reversed(videos))


async def peertube(p, source):
    parts = urlsplit(source)
    base = f"https://{parts.netloc}"
    handle = quote(parts.path.rstrip("/").rsplit("/", 1)[1], safe="")
    videos, more = [], False
    for page in range(p.max_pages):
        data = await p.json("GET", f"{base}/api/v1/video-channels/{handle}/videos",
                            params={"start": page * 100, "count": 100, "sort": "-publishedAt",
                                    "isLive": "false"})
        videos.extend(item(v["uuid"], v["name"], v.get("url") or f"{base}/videos/watch/{v['uuid']}",
                           v["publishedAt"]) for v in data["data"] if not v.get("isLive", False)
                      and v.get("privacy", {}).get("id") == 1)
        more = (page + 1) * 100 < data["total"]
        if not more:
            break
    p.windows[("peertube", source)] = more
    return list(reversed(videos))
