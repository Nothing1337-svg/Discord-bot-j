import io
from types import SimpleNamespace as NS

from PIL import Image

from bot.banner import render
from bot.voice import BannerSchedule, voice_count


def test_voice_count():
    human = NS(id=1, bot=False)
    bot = NS(id=2, bot=True)
    afk = NS(members=[NS(id=3, bot=False)])
    guild = NS(voice_channels=[NS(members=[human, bot]), afk],
               stage_channels=[NS(members=[human, NS(id=4, bot=False)])], afk_channel=afk)
    assert voice_count(guild) == 2
    assert voice_count(guild, exclude_afk=False) == 3


def test_debounce_cooldown_retry_and_return_to_previous_value():
    now = [0]
    schedule = BannerSchedule(5, 60, lambda: now[0])
    schedule.observe(1)
    now[0] = 4
    schedule.observe(2)
    now[0] = 8
    assert not schedule.due()
    now[0] = 9
    assert schedule.due()
    schedule.attempted()
    schedule.success(2)
    schedule.observe(3)
    now[0] = 68
    assert not schedule.due()
    now[0] = 69
    assert schedule.due()
    schedule.attempted()  # failed upload
    now[0] = 128
    assert not schedule.due()
    now[0] = 129
    assert schedule.due()
    schedule.observe(2)
    assert not schedule.due()


def test_change_during_upload():
    now = [0]
    schedule = BannerSchedule(5, 60, lambda: now[0])
    schedule.observe(1)
    now[0] = 5
    schedule.attempted()
    schedule.observe(2)
    schedule.success(1)
    now[0] = 65
    assert schedule.due()


def test_render_languages_unicode_and_large_count():
    for language in ("ru", "en"):
        data = render(123456, language, title="Привет 🎮 🚀 e\u0301 👨‍👩‍👧‍👦 漢字")
        image = Image.open(io.BytesIO(data))
        assert image.size == (960, 540)
        assert image.format == "PNG"
        assert image.getbbox() == (0, 0, 960, 540)
