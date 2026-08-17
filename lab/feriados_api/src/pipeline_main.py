import asyncio
import os

from src.client import FeriadosClient
from src.crawler import FeriadosCrawler

from src.pipeline.config import PipelineConfig
from src.pipeline.core import HolidayPipeline
from src.exporters.duckdb import export_duckdb
from src.exporters.dim_holiday_duckdb import export_dim_holiday
from src.transformers.dim_holiday import build_dim_holiday

async def main():
    API_KEY = os.environ["FERIADOS_API_KEY"]
    YEAR=2026

    config = PipelineConfig(
        year=YEAR,
        exporters=[
            "duckdb",
            "csv",
            "json",
        ],
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

        # Populates holiday_key on each record in place, so the
        # `holidays` export below already carries the FK to dim_holiday.
        dim_holidays = build_dim_holiday(holidays)

        export_duckdb(
            holidays,
            config.duckdb_path,
        )

        export_dim_holiday(
            dim_holidays,
            config.duckdb_path,
        )

        print(
            f"Exported {len(holidays)} holidays to {config.duckdb_path}"
        )

        merged = sum(
            1
            for d in dim_holidays
            if len(d.aliases) > 1
        )

        print(
            f"dim_holiday: {len(dim_holidays)} canonical holidays "
            f"({merged} with aliases merged)"
        )


if __name__ == "__main__":
    asyncio.run(main())