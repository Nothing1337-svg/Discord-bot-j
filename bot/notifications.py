import asyncio
import logging
import time

log = logging.getLogger(__name__)


class Notifier:
    def __init__(self, store, providers, send, max_send=5, interval=120, clock=time.monotonic):
        self.store, self.providers, self.send = store, providers, send
        self.max_send, self.interval, self.clock = max_send, interval, clock
        self.lock = asyncio.Lock()
        self.fetch_failures = {}
        self.delivery_failures = {}
        self.last_success = None

    @property
    def failures(self):
        return {**self.fetch_failures, **self.delivery_failures}

    def forget(self, sub_id):
        self.fetch_failures.pop(sub_id, None)
        self.delivery_failures.pop(sub_id, None)

    def ready(self, failures, sub_id):
        return self.clock() >= failures.get(sub_id, (0, 0))[1]

    def failed(self, failures, sub_id, stage, exc):
        count = failures.get(sub_id, (0, 0))[0] + 1
        delay = max(min(3600, self.interval * 2 ** min(count, 5)), getattr(exc, "retry_after", 0))
        failures[sub_id] = (count, self.clock() + delay)
        # Never log source URLs, headers, tokens or upstream response bodies.
        log.warning('Subscription %s %s failed (%s); retry in %ss', sub_id, stage, type(exc).__name__, delay)

    async def poll(self):
        async with self.lock:
            for sub in self.store.all():
                if self.ready(self.fetch_failures, sub.id):
                    try:
                        videos = await self.providers.fetch(sub.kind, sub.source)
                        self.store.enqueue(sub.id, videos)
                        self.fetch_failures.pop(sub.id, None)
                        self.last_success = time.time()
                    except Exception as exc:  # noqa: BLE001 - isolate sources; redact secrets
                        self.failed(self.fetch_failures, sub.id, 'fetch', exc)
                # Delivery is independent: upstream outages must not block durable pending items.
                # Conversely, Discord outages must not stop collecting newly published videos.
                if self.ready(self.delivery_failures, sub.id):
                    try:
                        for video in self.store.pending(sub.id, self.max_send):
                            await self.send(sub, video)
                            # Mark only after Discord acknowledges delivery.
                            self.store.mark(sub.id, video.id)
                        self.delivery_failures.pop(sub.id, None)
                    except Exception as exc:  # noqa: BLE001 - isolate destinations; redact secrets
                        self.failed(self.delivery_failures, sub.id, 'delivery', exc)
