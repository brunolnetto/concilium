from __future__ import annotations

import asyncio
import time


class AsyncRateLimiter:

    def __init__(
        self,
        requests_per_minute: int = 60,
    ):
        self.interval = (
            60 / requests_per_minute
        )

        self._lock = asyncio.Lock()
        self._last_request = 0.0


    async def acquire(self):

        async with self._lock:

            now = time.monotonic()

            elapsed = (
                now -
                self._last_request
            )

            wait = (
                self.interval -
                elapsed
            )

            if wait > 0:
                await asyncio.sleep(wait)

            self._last_request = (
                time.monotonic()
            )