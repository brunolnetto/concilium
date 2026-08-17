import asyncio
import os

from src.client import FeriadosClient
from src.crawler import FeriadosCrawler

from src.pipeline.config import PipelineConfig
from src.pipeline.core import HolidayPipeline
from src.exporters.duckdb import export_duckdb
from src.exporters.dim_holiday_duckdb import export_dim_holiday
from src.transformers.dim_holiday import build_dim_holiday

# 2017..2026 inclusive (10 years). Checkpoint-cached, so a re-run only
# fetches years/states/capitals not already marked SUCCESS.
YEARS = range(2017, 2027)

DUCKDB_PATH = "holidays.duckdb"


async def main():
    API_KEY = os.environ["FERIADOS_API_KEY"]

    all_holidays = []


    async with FeriadosClient(API_KEY) as client:

        crawler = FeriadosCrawler(
            client,
            workers=5,
        )

        for year in YEARS:

            print(f"\n=== {year} ===")

            config = PipelineConfig(
                year=year,
                duckdb_path=DUCKDB_PATH,
            )

            pipeline = HolidayPipeline(
                crawler,
                config,
            )

            holidays = await pipeline.run()

            all_holidays.extend(holidays)

            print(f"{year}: {len(holidays)} holidays")


    # export_duckdb replaces the whole `holidays` table, so the full
    # multi-year set is accumulated in memory and written once here —
    # dim_holiday is upserted per (holiday_key, year), so it's safe
    # either way, but keeping both writes together keeps the two
    # tables consistent with each other.

    dim_holidays = build_dim_holiday(all_holidays)

    export_duckdb(
        all_holidays,
        DUCKDB_PATH,
    )

    export_dim_holiday(
        dim_holidays,
        DUCKDB_PATH,
    )

    print(
        f"\nTotal: {len(all_holidays)} holidays across {len(YEARS)} years "
        f"({YEARS.start}-{YEARS.stop - 1}), {len(dim_holidays)} canonical entries"
    )


if __name__ == "__main__":
    asyncio.run(main())
