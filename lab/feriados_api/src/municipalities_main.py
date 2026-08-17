import asyncio
import os

from src.client import FeriadosClient
from src.crawler import FeriadosCrawler

from src.pipeline.config import PipelineConfig
from src.pipeline.core import HolidayPipeline
from src.exporters.duckdb import export_duckdb

# Requires a plan with municipality quota (e.g. Dev, 5.000 req/month) —
# non-capital cities return 403 (Upgrade required) on the Free plan.
#
# With one request per non-capital municipality (5.543 cities), a full
# crawl needs ~5.543 requests — just over a single month's 5.000 quota.
# Re-running this after the quota resets picks up where it left off,
# since already-crawled cities are cached in the crawl checkpoint.

async def main():
    API_KEY = os.environ["FERIADOS_API_KEY"]
    YEAR = 2026

    config = PipelineConfig(
        year=YEAR,
        duckdb_path="holidays.duckdb",
        include_municipalities=True,
    )


    async with FeriadosClient(API_KEY) as client:

        crawler = FeriadosCrawler(
            client,
            workers=5,
        )


        pipeline = HolidayPipeline(
            crawler,
            config,
        )


        holidays = await pipeline.run()


        export_duckdb(
            holidays,
            config.duckdb_path,
        )

        print(
            f"Exported {len(holidays)} holidays to {config.duckdb_path}"
        )


if __name__ == "__main__":
    asyncio.run(main())
