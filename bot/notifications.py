import asyncio
import logging
import time

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, store, providers, send, max_send=5, interval=120, clock=time.monotonic):
        self.store, self.providers, self.send = store, providers, send
        self.max_send, self.interval, self.clock = max_send, interval, clock
        self.lock = asyncio.Lock()
        self.failures = {}
        self.last_success = None

    async def poll(self):
        async with self.lock:
            for sub in self.store.all():
                failures, retry_at = self.failures.get(sub.id, (0, 0))
                if self.clock() < retry_at:
                    continue
                try:
                    videos = await self.providers.fetch(sub.kind, sub.source)
                    self.store.enqueue(sub.id, videos)
                    for video in self.store.pending(sub.id, self.max_send):
                        await self.send(sub, video)
                        # Mark only after Discord acknowledges delivery.
                        self.store.mark(sub.id, video.id)
                    self.failures.pop(sub.id, None)
                    self.last_success = time.time()
                except Exception as exc:  # noqa: BLE001 - isolate subscriptions; redact secrets
                    failures += 1
                    delay = min(3600, self.interval * 2 ** min(failures, 5))
                    self.failures[sub.id] = (failures, self.clock() + delay)
                    # Never log source URLs, headers, tokens or upstream response bodies.
                    log.warning("Subscription %s failed (%s); retry in %ss", sub.id, type(exc).__name__, delay)
