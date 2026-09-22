import time


def voice_count(guild, exclude_afk=True):
    """Current human participants, including muted/deafened members and Stage audience."""
    return len({member.id for channel in [*guild.voice_channels, *guild.stage_channels]
                if not (exclude_afk and channel == guild.afk_channel)
                for member in channel.members if not member.bot})


class BannerSchedule:
    def __init__(self, debounce=5, cooldown=60, clock=time.monotonic):
        self.debounce, self.cooldown, self.clock = debounce, cooldown, clock
        self.value = None
        self.sent = None
        self.changed_at = 0
        self.last_attempt = float("-inf")

    def observe(self, value):
        if value != self.value:
            self.value = value
            self.changed_at = self.clock()

    def due(self):
        now = self.clock()
        return (self.value is not None and self.value != self.sent
                and now - self.changed_at >= self.debounce
                and now - self.last_attempt >= self.cooldown)

    def attempted(self):
        self.last_attempt = self.clock()

    def success(self, value):
        self.sent = value
