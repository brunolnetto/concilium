from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from ..client import FeriadosClient

from .capitals import STATE_CAPITALS
from .checkpoint import CrawlCheckpoint
from .models import (
    CrawlResult,
    CrawlScope,
    CrawlTask,
    CrawlStatus,
)

from .queue import CrawlQueue
from .worker import CrawlWorker


class FeriadosCrawler:

    def __init__(
        self,
        client: FeriadosClient,
        *,
        workers: int = 5,
        checkpoint: str = "crawler.db",
    ):
        self.client = client
        self.workers = workers

        self.checkpoint = CrawlCheckpoint(
            checkpoint
        )


    async def crawl(
        self,
        tasks: list[CrawlTask],
    ) -> AsyncIterator[CrawlResult]:

        queue = CrawlQueue()

        result_queue: asyncio.Queue[
            CrawlResult
        ] = asyncio.Queue()


        #
        # Enqueue tasks
        #

        for task in tasks:
            await queue.put(task)


        #
        # Start workers
        #

        workers = [
            asyncio.create_task(
                CrawlWorker(
                    client=self.client,
                    queue=queue,
                    results=result_queue,
                    checkpoint=self.checkpoint,
                ).run()
            )
            for _ in range(self.workers)
        ]


        #
        # Consume results
        #

        remaining = len(tasks)

        try:

            while remaining > 0:

                result = await result_queue.get()

                remaining -= 1

                yield result


        finally:

            #
            # Stop workers
            #

            for worker in workers:
                worker.cancel()


            await asyncio.gather(
                *workers,
                return_exceptions=True,
            )


    async def crawl_national(
        self,
        year: int,
    ) -> AsyncIterator[CrawlResult]:

        tasks = [
            CrawlTask(
                year=year,
                scope=CrawlScope.NATIONAL,
            )
        ]

        async for result in self.crawl(tasks):
            yield result



    async def crawl_states(
        self,
        year: int,
    ) -> AsyncIterator[CrawlResult]:

        response = await self.client.states()


        tasks = [
            CrawlTask(
                year=year,
                scope=CrawlScope.STATE,
                uf=state["uf"],
            )
            for state in response["estados"]
        ]


        async for result in self.crawl(tasks):
            yield result


    async def crawl_municipalities(
        self,
        year: int,
    ) -> AsyncIterator[CrawlResult]:

        # Requires a plan with municipality quota (e.g. Dev, 5.000
        # req/month) — non-capital cities return 403 on the Free plan.

        municipalities = await self.client.all_municipalities()

        tasks = [
            CrawlTask(
                year=year,
                scope=CrawlScope.MUNICIPALITY,
                ibge=municipality["ibge"],
            )
            for municipality in municipalities
        ]

        async for result in self.crawl(tasks):
            yield result


    async def crawl_capitals(
        self,
        year: int,
    ) -> AsyncIterator[CrawlResult]:

        # Only the 27 state capitals are available on the current
        # API plan; other municipalities return 403 (Upgrade required).

        tasks = [
            CrawlTask(
                year=year,
                scope=CrawlScope.MUNICIPALITY,
                ibge=ibge,
            )
            for ibge in STATE_CAPITALS.values()
        ]

        async for result in self.crawl(tasks):
            yield result