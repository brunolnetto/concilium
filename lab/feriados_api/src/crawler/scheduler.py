from __future__ import annotations

import asyncio

from .models import CrawlTask


class CrawlScheduler:

    def __init__(self):
        self.queue: asyncio.Queue[CrawlTask] = (
            asyncio.Queue()
        )


    async def submit(
        self,
        task: CrawlTask,
    ):

        await self.queue.put(task)


    async def get(
        self,
    ) -> CrawlTask:

        return await self.queue.get()


    def task_done(self):

        self.queue.task_done()


    async def join(self):

        await self.queue.join()