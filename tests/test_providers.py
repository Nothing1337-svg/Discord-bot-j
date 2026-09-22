import json
from unittest.mock import AsyncMock

import pytest

from bot.providers import MAX_BODY, Providers, PublicResolver, normalize, parse_feed, public_url


@pytest.mark.parametrize("url", ["http://example.org", "https://localhost/feed", "https://127.0.0.1",
                                      "https://[::1]", "https://10.0.0.1", "https://a:b@example.org",
                                      "https://example.org:8080", "file:///etc/passwd"])
def test_unsafe_urls(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_normalization():
    assert normalize("twitch", "https://www.twitch.tv/Example/") == "example"
    assert normalize("youtube", "https://www.youtube.com/channel/UC" + "a" * 22) == "UC" + "a" * 22
    assert normalize("youtube", "https://www.youtube.com/@creator") == "@creator"
    with pytest.raises(ValueError):
        normalize("unknown", "creator")


def test_atom_unicode_and_order():
    body = '''<?xml version="1.0" encoding="utf-8"?>
    <feed xmlns="http://www.w3.org/2005/Atom"><title>Videos</title>
    <entry><id>new</id><title>Привет 🎮</title><link href="https://example.org/new"/></entry>
    <entry><id>old</id><title>Old</title><link href="https://example.org/old"/></entry></feed>'''.encode()
    videos = parse_feed(body)
    assert [v.id for v in videos] == ["old", "new"]
    assert videos[1].title == "Привет 🎮"


def test_rss_and_bad_feed():
    videos = parse_feed(b'<rss version="2.0"><channel><title>test</title><item><guid>1</guid>'
                        b'<title>Video</title><link>https://example.org/v</link></item></channel></rss>')
    assert videos[0].id == "1"
    with pytest.raises(ValueError):
        parse_feed(b"<html>not RSS</html>")


@pytest.mark.parametrize("url", ["https://example.org/" + "a" * 2000, "https://example.org/a\nb"])
def test_unsendable_url_is_rejected(url):
    with pytest.raises(ValueError):
        public_url(url)


def test_feed_with_no_usable_links_is_not_accepted_as_empty():
    with pytest.raises(ValueError, match="no usable"):
        parse_feed(b'<rss version="2.0"><channel><item><guid>1</guid>'
                   b'<link>http://example.org/video</link></item></channel></rss>')


async def test_twitch_token_cache(monkeypatch):
    monkeypatch.setenv("TWITCH_CLIENT_ID", "test-client")
    monkeypatch.setenv("TWITCH_CLIENT_SECRET", "test-secret")
    provider = Providers(None)
    provider.request = AsyncMock(side_effect=[
        json.dumps({"access_token": "test-token", "expires_in": 3600}).encode(),
        b'{"data":[{"id":"1"}]}',
        b'{"data":[{"id":"v","title":"Video","url":"https://www.twitch.tv/videos/1"}]}',
    ])
    videos = await provider.fetch("twitch", "creator")
    assert videos[0].id == "v"
    assert (await provider.twitch_headers())["Authorization"] == "Bearer test-token"
    assert provider.request.await_count == 3


async def test_dns_blocks_private_answer(monkeypatch):
    monkeypatch.setattr("aiohttp.resolver.DefaultResolver.resolve", AsyncMock(return_value=[{"host": "127.0.0.1"}]))
    resolver = PublicResolver()
    with pytest.raises(ValueError):
        await resolver.resolve("example.org")
    await resolver.close()


@pytest.mark.parametrize("status,body,expected", [(302, b"", "HTTP 302"), (429, b"", "HTTP 429"),
                                                (200, b"x" * (MAX_BODY + 1), "2 MiB")])
async def test_http_limits_and_redirects(status, body, expected):
    from unittest.mock import MagicMock

    async def chunks(size):
        yield body

    response = MagicMock()
    response.status = status
    response.content.iter_chunked = chunks
    context = AsyncMock()
    context.__aenter__.return_value = response
    session = MagicMock()
    session.request.return_value = context
    provider = Providers(session)
    with pytest.raises(ValueError, match=expected):
        await provider.request("GET", "https://example.org/feed")
    assert session.request.call_args.kwargs["allow_redirects"] is False
