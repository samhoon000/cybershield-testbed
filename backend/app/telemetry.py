"""Best-effort, payload-free HTTP telemetry transport."""

import asyncio
import hashlib
import hmac
import json
import logging
import time
from dataclasses import asdict, dataclass
from random import uniform
from uuid import uuid4

import httpx

PATH = "/v1/http-events"
QUEUE_SIZE = 512
BATCH_SIZE = 32
HEARTBEAT_SECONDS = 15
RETRYABLE = {408, 425, 429}
logger = logging.getLogger(__name__)


@dataclass
class Delivery:
    sent: int = 0
    dropped: int = 0
    retries: int = 0
    failed_batches: int = 0


class TelemetrySender:
    def __init__(self, url, app, key, *, queue_size=QUEUE_SIZE):
        self.url = url
        self.app = app
        self.key = key
        self.queue = asyncio.Queue(maxsize=queue_size)
        self.health = Delivery()

    def submit(self, event):
        try:
            self.queue.put_nowait(event)
        except asyncio.QueueFull:
            self.health.dropped += 1

    async def run(self):
        async with httpx.AsyncClient(timeout=5, follow_redirects=False, trust_env=False) as client:
            while True:
                events = []
                try:
                    async with asyncio.timeout(HEARTBEAT_SECONDS):
                        events.append(await self.queue.get())
                except TimeoutError:
                    pass
                if events:
                    # Coalesce concurrent requests without adding noticeable dashboard lag.
                    await asyncio.sleep(0.25)
                    while len(events) < BATCH_SIZE and not self.queue.empty():
                        events.append(self.queue.get_nowait())
                if not await self.deliver(client, events):
                    await asyncio.sleep(5)

    async def deliver(self, client, events):
        retry_delay = 0.0
        for attempt in range(3):
            if attempt:
                await asyncio.sleep(retry_delay)
                self.health.retries += 1
            body = json.dumps({
                "version": 1,
                "events": events,
                "delivery": {**asdict(self.health), "queued": self.queue.qsize()},
            }, separators=(",", ":"), allow_nan=False).encode()
            timestamp = str(int(time.time()))
            nonce = str(uuid4())
            canonical = "\n".join(("POST", PATH, self.app, timestamp, nonce,
                                   hashlib.sha256(body).hexdigest()))
            headers = {
                "content-type": "application/json",
                "x-telemetry-app": self.app,
                "x-telemetry-timestamp": timestamp,
                "x-telemetry-nonce": nonce,
                "x-telemetry-signature": hmac.new(self.key, canonical.encode(), hashlib.sha256).hexdigest(),
            }
            retry_delay = 0.5 * (2 ** attempt) + uniform(0, 0.25)
            try:
                async with asyncio.timeout(5):
                    response = await client.post(self.url, content=body, headers=headers)
            except (httpx.RequestError, TimeoutError):
                continue
            if response.status_code == 200:
                self.health.sent += len(events)
                return True
            if response.status_code not in RETRYABLE and response.status_code < 500:
                break
            retry_after = response.headers.get("retry-after", "")
            if retry_after.isascii() and retry_after.isdecimal() and len(retry_after) <= 5:
                retry_delay = max(retry_delay, min(5, int(retry_after)))
        self.health.failed_batches += 1
        self.health.dropped += len(events)
        logger.warning("HTTP telemetry delivery failed for application %s", self.app)
        return False
