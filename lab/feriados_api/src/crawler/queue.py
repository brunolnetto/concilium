from __future__ import annotations

import asyncio

from .models import CrawlTask


class CrawlQueue:

    def __init__(self):

        self._queue: asyncio.Queue[CrawlTask] = (
            asyncio.Queue()
        )


    @property
    def queue(self) -> asyncio.Queue[CrawlTask]:
        return self._queue


    async def put(
        self,
        task: CrawlTask,
    ):

        await self._queue.put(
            task
        )


    async def get(
        self,
    ) -> CrawlTask:

        return await self._queue.get()


    def task_done(
        self,
    ):

        self._queue.task_done()


    async def join(
        self,
    ):

        await self._queue.join()
