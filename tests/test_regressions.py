import asyncio
import sqlite3
from email.utils import formatdate
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.config import Config
from bot.main import VideoBot
from bot.providers import Providers, UpstreamError, Video, parse_feed
from bot.store import Store


def client():
    return VideoBot(Config('test-only', 123, 'ru', 120, 5, False, 5, 60, Path('unused'), True))


def test_same_second_publication_is_not_lost(tmp_path):
    store = Store(tmp_path / 'db')
    sid = store.add('rss', 'https://example.org/feed', 1, [], created_at=1000.8)
    store.enqueue(sid, [Video('new', 'New', 'https://example.org/video', 1000)])
    assert len(store.pending(sid, 5)) == 1
    store.close()


def test_empty_rss_guids_fall_back_to_distinct_links():
    feed = b'''<rss version="2.0"><channel><title>Videos</title>
    <item><guid></guid><link>https://example.org/1</link></item>
    <item><guid></guid><link>https://example.org/2</link></item>
    </channel></rss>'''
    videos = parse_feed(feed)
    assert len({v.id for v in videos}) == 2
    assert all(v.id for v in videos)


async def test_retry_after_http_date_is_honoured(monkeypatch):
    monkeypatch.setattr('bot.providers.time.time', lambda: 1000)
    response = MagicMock()
    response.status = 429
    response.headers = {'Retry-After': formatdate(4600, usegmt=True)}
    context = AsyncMock()
    context.__aenter__.return_value = response
    session = MagicMock()
    session.request.return_value = context
    with pytest.raises(UpstreamError) as error:
        await Providers(session).request('GET', 'https://example.org/feed')
    assert error.value.retry_after == 3600


async def test_poll_worker_survives_database_error():
    bot = client()
    bot.notifier = AsyncMock()
    bot.notifier.poll.side_effect = sqlite3.OperationalError('database is locked')
    await bot.poll_loop.coro(bot)
    assert bot.poll_error
    bot.notifier.poll.side_effect = None
    await bot.poll_loop.coro(bot)
    assert not bot.poll_error
    await bot.close()


async def test_shutdown_cancels_check_before_closing_database():
    bot = client()
    started = asyncio.Event()
    async def pending_poll():
        started.set()
        await asyncio.Event().wait()
    bot.notifier = SimpleNamespace(poll=pending_poll)
    bot.store = MagicMock()
    bot.session = AsyncMock()
    interaction = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    command = bot.tree.get_command('check', guild=bot.scope)
    task = asyncio.create_task(command.callback(interaction))
    await started.wait()
    try:
        await bot.close()
        assert task.done(), 'Command still running after DB and HTTP session closed'
        assert task.cancelled()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


def test_process_lock_blocks_second_instance_and_releases(tmp_path):
    from bot.process_lock import ProcessLock
    path = tmp_path / 'bot.lock'
    first = ProcessLock(path)
    with pytest.raises(RuntimeError, match='Another bot process'):
        ProcessLock(path)
    first.close()
    second = ProcessLock(path)
    second.close()
    second.close()  # shutdown is idempotent
    assert path.exists()  # Never unlink the inode while another process might be opening it.


@pytest.mark.parametrize('headers,expected', [
    ({'Retry-After': 'invalid', 'Ratelimit-Reset': '2000'}, 1000),
    ({'Retry-After': 'nan'}, 0),
    ({'Retry-After': 'inf'}, 0),
    ({'Retry-After': '-5'}, 0),
    ({'Retry-After': '1000000'}, 86400),
])
def test_bad_retry_header_cannot_break_other_reset_header(headers, expected):
    from bot.providers import retry_delay
    assert retry_delay(headers, 1000) == expected


async def test_startup_failure_releases_http_session_and_process_lock(monkeypatch, tmp_path):
    from bot import main
    from bot.process_lock import ProcessLock
    monkeypatch.setattr(main, 'ROOT', tmp_path)
    bot = client()
    bot.tree.sync = AsyncMock(side_effect=RuntimeError('sync failed'))
    with pytest.raises(RuntimeError, match='sync failed'):
        await bot.setup_hook()
    await bot.close()
    assert bot.session.closed
    new_lock = ProcessLock(tmp_path / 'data' / 'bot.lock')
    new_lock.close()
    await bot.close()


async def test_commands_rejected_during_shutdown():
    bot = client()
    await bot.close()
    command = bot.tree.get_command('check', guild=bot.scope)
    with pytest.raises(ValueError, match='stopping'):
        await command.callback(MagicMock())


async def test_status_reports_database_failure_without_querying_more():
    bot = client()
    bot.store = MagicMock()
    bot.store.all.side_effect = sqlite3.OperationalError('locked')
    interaction = MagicMock()
    interaction.response.send_message = AsyncMock()
    command = bot.tree.get_command('status', guild=bot.scope)
    await command.callback(interaction)
    assert interaction.response.send_message.call_args.args[0] == bot.text('poll_error')
    bot.store.pending_count.assert_not_called()
    await bot.close()


@pytest.mark.parametrize('login_failure', [False, True])
async def test_runner_shutdown_signal_and_failed_login(monkeypatch, login_failure):
    from bot import main
    handlers = {}
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, 'add_signal_handler', lambda sig, cb: handlers.update({sig: cb}))
    monkeypatch.setattr(loop, 'remove_signal_handler', lambda sig: handlers.pop(sig))
    closed = []
    async def start(token):
        if login_failure:
            raise RuntimeError('login failed')
        handlers[main.signal.SIGTERM]()
        await asyncio.Event().wait()
    fake = AsyncMock()
    fake.start.side_effect = start
    fake.__aenter__.return_value = fake
    async def cleanup(*args):
        closed.append(True)
    fake.__aexit__.side_effect = cleanup
    monkeypatch.setattr(main, 'VideoBot', lambda config, connector: fake)
    monkeypatch.setattr(main.aiohttp, 'TCPConnector', lambda **kwargs: None)
    if login_failure:
        with pytest.raises(RuntimeError, match='login failed'):
            await main.run_bot(client().config)
    else:
        await main.run_bot(client().config)
    assert closed == [True]
    assert handlers == {}


def test_process_lock_is_effective_across_processes(tmp_path):
    import subprocess
    import sys

    from bot.process_lock import ProcessLock
    path = tmp_path / 'bot.lock'
    guard = ProcessLock(path)
    code = '''from pathlib import Path
import sys
from bot.process_lock import ProcessLock
try:
    lock = ProcessLock(Path(sys.argv[1]))
except RuntimeError:
    print("blocked")
else:
    print("acquired")
    lock.close()
'''
    result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'blocked'
    guard.close()
    result = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True, text=True, check=True)
    assert result.stdout.strip() == 'acquired'
