from __future__ import annotations

import asyncio
import json
from dataclasses import asdict
from datetime import date
from uuid import UUID

from ..client import FeriadosClient
from ..models import Holiday

from .capitals import STATE_CAPITALS
from .checkpoint import CrawlCheckpoint
from .queue import CrawlQueue

from .models import (
    CrawlResult,
    CrawlScope,
    CrawlStatus,
)


class CrawlWorker:


    def __init__(
        self,
        *,
        client: FeriadosClient,
        queue: CrawlQueue,
        results: asyncio.Queue[CrawlResult],
        checkpoint: CrawlCheckpoint,
    ):

        self.client = client
        self.queue = queue
        self.results = results
        self.checkpoint = checkpoint



    async def run(self) -> None:


        while True:

            task = await self.queue.get()


            try:


                if self.checkpoint.is_done(task):

                    cached = self.checkpoint.get_payload(
                        task
                    )

                    payload = (
                        self.deserialize_payload(cached)
                        if cached
                        else None
                    )

                    await self.results.put(
                        CrawlResult(
                            task=task,
                            status=CrawlStatus.SKIPPED,
                            payload=payload,
                            records=len(payload) if payload else 0,
                        )
                    )

                    continue



                self.checkpoint.save(
                    task,
                    CrawlStatus.RUNNING,
                )



                payload = await self.execute(
                    task
                )


                records = self.count_records(
                    payload
                )



                self.checkpoint.save(
                    task,
                    CrawlStatus.SUCCESS,
                    records=records,
                    payload=self.serialize_payload(payload),
                )



                await self.results.put(
                    CrawlResult(
                        task=task,
                        status=CrawlStatus.SUCCESS,
                        payload=payload,
                        records=records,
                    )
                )



            except asyncio.CancelledError:

                raise



            except Exception as exc:


                self.checkpoint.save(
                    task,
                    CrawlStatus.FAILED,
                    error=str(exc),
                )


                await self.results.put(
                    CrawlResult(
                        task=task,
                        status=CrawlStatus.FAILED,
                        error=exc,
                    )
                )



            finally:

                self.queue.task_done()



    async def execute(
        self,
        task,
    ):

        # `facultativos=true` replaces ESTADUAL/MUNICIPAL entries with
        # FACULTATIVO ones instead of adding to them, so both the
        # compulsory and the facultativo sets must be fetched and
        # merged (downstream dedup by `Holiday.id` removes the overlap,
        # e.g. NACIONAL holidays present in both responses).

        match task.scope:

            case CrawlScope.NATIONAL:

                compulsorio = await self.client.national_holidays(
                    task.year
                )

                facultativo = await self.client.national_holidays(
                    task.year,
                    facultativos=True,
                )

                return compulsorio + facultativo


            case CrawlScope.STATE:

                compulsorio = await self.client.state_holidays(
                    task.uf,
                    task.year,
                )

                facultativo = await self.client.state_holidays(
                    task.uf,
                    task.year,
                    facultativos=True,
                )

                return compulsorio + facultativo


            case CrawlScope.MUNICIPALITY:

                compulsorio = await self.client.city_holidays(
                    task.ibge,
                    task.year,
                )

                # Capitals are free, so fetch facultativos there too.
                # Other municipalities consume plan quota (e.g. 5.000
                # req/month on Dev) — one call each keeps the full
                # 5.543-city crawl close to a single month's budget.

                if task.ibge not in STATE_CAPITALS.values():
                    return compulsorio

                facultativo = await self.client.city_holidays(
                    task.ibge,
                    task.year,
                    facultativos=True,
                )

                return compulsorio + facultativo


            case _:

                raise ValueError(
                    f"Unknown scope: {task.scope}"
                )



    @staticmethod
    def serialize_payload(payload) -> str | None:

        if not isinstance(payload, list):
            return None

        return json.dumps(
            [asdict(item) for item in payload],
            default=str,
        )


    @staticmethod
    def deserialize_payload(raw: str) -> list[Holiday]:

        items = json.loads(raw)

        return [
            Holiday(
                id=UUID(item["id"]),
                date=date.fromisoformat(item["date"]),
                name=item["name"],
                type=item["type"],
                description=item["description"],
                uf=item["uf"],
                ibge_code=item["ibge_code"],
                banking=item["banking"],
            )
            for item in items
        ]


    @staticmethod
    def count_records(payload) -> int:


        if isinstance(payload, list):

            return len(payload)



        if isinstance(payload, dict):

            for key in (
                "feriados",
                "holidays",
                "data",
            ):

                value = payload.get(key)

                if isinstance(value, list):

                    return len(value)


        return 0