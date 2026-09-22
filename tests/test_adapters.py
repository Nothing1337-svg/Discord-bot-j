import json
import time
from unittest.mock import AsyncMock

import pytest

from bot.accounts import Accounts
from bot.providers import Providers, normalize


@pytest.fixture
def provider(tmp_path, monkeypatch):
    monkeypatch.setenv("TEST_ACCOUNT_TOKEN", "test-token-never-log")
    path = tmp_path / "accounts.json"
    path.write_text(json.dumps({kind: {"platform": kind, "token_env": "TEST_ACCOUNT_TOKEN", "user_id": "123",
                                      "api_version": "v24.0"} for kind in ("tiktok", "instagram", "vimeo")}))
    return Providers(None, Accounts(path))


async def test_tiktok_paginates_and_sends_only_to_fixed_api(provider):
    provider.json = AsyncMock(side_effect=[
        {"error": {"code": "ok"}, "data": {"videos": [
            {"id": "new", "title": "New 🎮", "share_url": "https://www.tiktok.com/@test/video/2", "create_time": 200}],
            "has_more": True, "cursor": 100}},
        {"error": {"code": "ok"}, "data": {"videos": [
            {"id": "old", "title": "Old", "share_url": "https://www.tiktok.com/@test/video/1", "create_time": 100}],
            "has_more": False}},
    ])
    videos = await provider.fetch("tiktok", "tiktok")
    assert [v.id for v in videos] == ["old", "new"]
    assert provider.json.call_args.kwargs["json"]["cursor"] == 100
    assert all(c.args[1] == "https://open.tiktokapis.com/v2/video/list/" for c in provider.json.call_args_list)
    assert not provider.windows[("tiktok", "tiktok")]


async def test_tiktok_http_200_error_does_not_create_baseline(provider):
    provider.json = AsyncMock(return_value={"error": {"code": "access_token_invalid", "message": "secret"}})
    with pytest.raises(ValueError, match="TikTok API rejected") as error:
        await provider.fetch("tiktok", "tiktok")
    assert "secret" not in str(error.value)


async def test_tiktok_page_limit_is_visible(provider):
    provider.max_pages = 1
    provider.json = AsyncMock(return_value={"error": {"code": "ok"},
                                           "data": {"videos": [], "has_more": True, "cursor": 1}})
    assert await provider.fetch("tiktok", "tiktok") == []
    assert provider.windows[("tiktok", "tiktok")]


async def test_instagram_skips_photos_and_does_not_follow_next_url(provider):
    provider.json = AsyncMock(side_effect=[
        {"data": [{"id": "photo", "media_type": "IMAGE"}, {"id": "reel", "media_type": "VIDEO",
                   "caption": "Reel", "permalink": "https://www.instagram.com/reel/test/",
                   "timestamp": "2026-09-22T00:00:00Z"}],
         "paging": {"next": "https://malicious.example/?access_token=secret", "cursors": {"after": "cursor"}}},
        {"data": [{"id": "carousel", "media_type": "CAROUSEL_ALBUM"}]},
    ])
    videos = await provider.fetch("instagram", "instagram")
    assert [v.id for v in videos] == ["reel"]
    assert provider.json.call_args.kwargs["params"]["after"] == "cursor"
    assert all(c.args[1] == "https://graph.instagram.com/v24.0/123/media" for c in provider.json.call_args_list)


async def test_vimeo_filters_private_unlisted_and_processing(provider):
    def video(id, privacy="anybody", status="available"):
        return {"uri": "/videos/" + id, "name": id, "link": "https://vimeo.com/" + id,
                "created_time": "2026-09-22T00:00:00Z", "privacy": {"view": privacy}, "status": status}
    provider.json = AsyncMock(return_value={"data": [video("1"), video("2", "nobody"), video("3", "unlisted"),
                                                    video("4", status="uploading")], "paging": {"next": None}})
    videos = await provider.fetch("vimeo", "vimeo")
    assert [v.id for v in videos] == ["/videos/1"]
    assert provider.json.call_args.kwargs["params"]["direction"] == "desc"


async def test_peertube_normalizes_and_filters_live_private(provider):
    source = normalize("peertube", "https://peertube.example/c/creator")
    assert source == "https://peertube.example/video-channels/creator"
    provider.json = AsyncMock(return_value={"total": 3, "data": [
        {"uuid": "1", "name": "Public", "publishedAt": "2026-09-22T00:00:00Z", "privacy": {"id": 1}},
        {"uuid": "2", "isLive": True, "privacy": {"id": 1}},
        {"uuid": "3", "privacy": {"id": 3}},
    ]})
    videos = await provider.fetch("peertube", source)
    assert [v.id for v in videos] == ["1"]
    assert videos[0].url == "https://peertube.example/videos/watch/1"
    assert "headers" not in provider.json.call_args.kwargs  # No account credentials sent to instances.


async def test_youtube_handle_resolves_to_canonical_id(provider, monkeypatch):
    monkeypatch.setenv("YOUTUBE_API_KEY", "test-api-key")
    provider.json = AsyncMock(return_value={"items": [{"id": "UC" + "a" * 22}]})
    assert await provider.resolve("youtube", "https://youtube.com/@creator") == "UC" + "a" * 22
    assert provider.json.call_args.kwargs["params"]["forHandle"] == "@creator"


async def test_youtube_handle_requires_key(provider, monkeypatch):
    monkeypatch.delenv("YOUTUBE_API_KEY", raising=False)
    with pytest.raises(ValueError, match="YOUTUBE_API_KEY"):
        await provider.resolve("youtube", "@creator")


@pytest.mark.parametrize("source", ["https://peertube.example/c/abc?token=x", "https://127.0.0.1/c/abc",
                                     "https://peertube.example/api/v1/videos", "https://peertube.example/c/../abc"])
def test_peertube_rejects_invalid_channel(source):
    with pytest.raises(ValueError):
        normalize("peertube", source)


def test_accounts_do_not_accept_wrong_platform_or_expired_token(provider):
    with pytest.raises(ValueError, match="wrong platform"):
        provider.accounts.get("instagram", "tiktok")
    data = json.loads(provider.accounts.path.read_text())
    data["tiktok"]["expires_at"] = time.time() - 1
    provider.accounts.path.write_text(json.dumps(data))
    with pytest.raises(ValueError, match="expired"):
        provider.accounts.get("tiktok", "tiktok")


def test_missing_account_token_is_actionable_and_redacted(provider, monkeypatch):
    monkeypatch.delenv("TEST_ACCOUNT_TOKEN")
    with pytest.raises(ValueError, match="token is missing"):
        provider.accounts.get("vimeo", "vimeo")


async def test_twitch_cursor_pagination(provider, monkeypatch):
    provider.twitch_headers = AsyncMock(return_value={"Authorization": "Bearer test"})
    provider.request = AsyncMock(return_value=b'{"data":[{"id":"1"}]}')
    provider.json = AsyncMock(side_effect=[
        {"data": [{"id": "new", "title": "New", "url": "https://www.twitch.tv/videos/2"}],
         "pagination": {"cursor": "next"}},
        {"data": [{"id": "old", "title": "Old", "url": "https://www.twitch.tv/videos/1"}], "pagination": {}},
    ])
    assert [v.id for v in await provider.fetch("twitch", "test")] == ["old", "new"]
    assert provider.json.call_args.kwargs["params"]["after"] == "next"


@pytest.mark.parametrize('url,expected', [
    ('https://youtube.com/@creator/videos?view=0', '@creator'),
    ('https://www.youtube.com/@creator/shorts', '@creator'),
    ('https://youtube.com/channel/UC' + 'a' * 22 + '/videos', 'UC' + 'a' * 22),
])
def test_youtube_channel_tabs(url, expected):
    assert normalize('youtube', url) == expected


async def test_authenticated_adapter_to_persistent_delivery(provider, tmp_path):
    from bot.notifications import Notifier
    from bot.store import Store
    now = int(time.time())
    old = {'id': 'old', 'title': 'Old', 'share_url': 'https://www.tiktok.com/@test/video/1', 'create_time': now-100}
    new = {'id': 'new', 'title': 'New', 'share_url': 'https://www.tiktok.com/@test/video/2', 'create_time': now+1}
    provider.json = AsyncMock(return_value={'error': {'code': 'ok'}, 'data': {'videos': [old], 'has_more': False}})
    store = Store(tmp_path / 'test.sqlite3')
    store.add('tiktok', 'tiktok', 1, await provider.fetch('tiktok', 'tiktok'))
    provider.json.return_value['data']['videos'] = [new, old]
    send = AsyncMock()
    notifier = Notifier(store, provider, send)
    await notifier.poll()
    await notifier.poll()
    assert send.await_count == 1
    assert send.call_args.args[1].id == 'new'
    store.close()
