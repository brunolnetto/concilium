import asyncio
import os
import time

from tqdm.auto import tqdm

from src.client import FeriadosClient
from src.crawler import (
    CrawlStatus,
    FeriadosCrawler,
)

API_KEY = os.environ["FERIADOS_API_KEY"]
YEAR = 2026


async def main():

    async with FeriadosClient(API_KEY) as client:

        crawler = FeriadosCrawler(
            client,
            workers=5,
        )

        print()
        print(f"Crawling state holidays ({YEAR})...")

        states = await client.states()

        total = states["total"]

        progress = tqdm(
            total=total,
            desc="States",
            unit="state",
        )

        started = time.perf_counter()

        success = 0
        failed = 0
        skipped = 0
        holiday_records = 0

        async for result in crawler.crawl_states(YEAR):

            progress.update(1)

            match result.status:

                case CrawlStatus.SUCCESS:

                    success += 1
                    holiday_records += result.records

                case CrawlStatus.SKIPPED:

                    skipped += 1
                    holiday_records += result.records

                case CrawlStatus.FAILED:

                    failed += 1

                    progress.write(
                        f"[FAILED] {result.task.uf}: {result.error}"
                    )

        progress.close()

        elapsed = time.perf_counter() - started

        print()
        print("=" * 50)
        print("CRAWL SUMMARY")
        print("=" * 50)
        print(f"States processed : {total}")
        print(f"Successful       : {success}")
        print(f"Skipped          : {skipped}")
        print(f"Failed           : {failed}")
        print(f"Holiday records  : {holiday_records}")
        print(f"Elapsed          : {elapsed:.2f} s")
        print("=" * 50)

        print()

        print("CHECKPOINT")

        print(
            crawler.checkpoint.stats()
        )


if __name__ == "__main__":
    asyncio.run(main())