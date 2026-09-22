import asyncio
import sqlite3
from unittest.mock import AsyncMock

import pytest

from bot.notifications import Notifier
from bot.providers import Video
from bot.store import Store


def video(id):
    return Video(id, "Ролик 🎮 " + id, "https://example.org/" + id)


@pytest.fixture
def store(tmp_path):
    db = Store(tmp_path / "test.sqlite3")
    yield db
    db.close()


async def test_baseline_dedup_and_restart(tmp_path):
    path = tmp_path / "test.sqlite3"
    db = Store(path)
    db.add("rss", "https://example.org/feed", 1, [video("old")])
    providers = AsyncMock()
    providers.fetch.return_value = [video("old"), video("new")]
    send = AsyncMock()
    await Notifier(db, providers, send).poll()
    db.close()
    db = Store(path)
    await Notifier(db, providers, send).poll()
    assert send.await_count == 1
    assert send.call_args.args[1].id == "new"
    db.close()


async def test_failed_send_retries_and_isolates_sources(store):
    first = store.add("rss", "https://example.org/a", 1, [])
    second = store.add("rss", "https://example.org/b", 2, [])
    providers = AsyncMock()
    providers.fetch.return_value = [video("new")]
    send = AsyncMock(side_effect=[RuntimeError(), None, None])
    now = [0]
    notifier = Notifier(store, providers, send, clock=lambda: now[0])
    await notifier.poll()
    assert not store.contains(first, "new")
    assert store.contains(second, "new")
    await notifier.poll()
    assert send.await_count == 2
    now[0] = 241
    await notifier.poll()
    assert store.contains(first, "new")
    assert not notifier.failures


async def test_queue_survives_feed_rollover_and_concurrent_checks(store):
    sid = store.add("rss", "https://example.org/feed", 1, [])
    providers = AsyncMock()
    providers.fetch.return_value = [video(str(i)) for i in range(8)]
    send = AsyncMock()
    notifier = Notifier(store, providers, send, max_send=2)
    await notifier.poll()
    providers.fetch.return_value = []
    await asyncio.gather(notifier.poll(), notifier.poll(), notifier.poll())
    assert send.await_count == 8
    assert len({call.args[1].id for call in send.call_args_list}) == 8
    assert store.pending(sid, 10) == []


def test_duplicate_subscription_and_cascade(store):
    sid = store.add("rss", "https://example.org/feed", 1, [video("old")])
    with pytest.raises(sqlite3.IntegrityError):
        store.add("rss", "https://example.org/feed", 1, [video("new")])
    assert not store.contains(sid, "new")
    store.enqueue(sid, [video("new")])
    assert store.remove(sid)
    assert not store.contains(sid, "old")
    assert store.pending(sid, 5) == []
    assert not store.remove(sid)


async def test_provider_failure_keeps_subscription(store):
    store.add("rss", "https://example.org/feed", 1, [])
    providers = AsyncMock()
    providers.fetch.side_effect = ValueError("broken XML")
    send = AsyncMock()
    notifier = Notifier(store, providers, send)
    await notifier.poll()
    assert len(store.all()) == 1
    assert len(notifier.failures) == 1
    send.assert_not_awaited()
