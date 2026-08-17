import asyncio
import os
from datetime import date, timedelta

from src.client import FeriadosClient
from src.business import BusinessCalendar
from src.generators.dim_calendar import (
    generate_dim_calendar,
)
from src.exporters import (
    calendar_to_polars,
    calendar_to_parquet,
)
from src.crawler import (
    FeriadosCrawler,
)

API_KEY = os.environ["FERIADOS_API_KEY"]

async def main():

    async with FeriadosClient(
        API_KEY
    ) as client:

        # --------------------------
        # Load calendar
        # --------------------------

        holiday_calendar = await client.calendar(
            2026,
            uf="GO",
        )


        # --------------------------
        # Holidays
        # --------------------------

        print("\n=== HOLIDAYS ===")

        for holiday in holiday_calendar.holidays():

            print(
                holiday.date,
                holiday.name,
                holiday.type,
            )


        # --------------------------
        # Date checks
        # --------------------------

        print("\n=== DATE CHECK ===")

        print(
            holiday_calendar.is_business_day(
                date(2026, 7, 26)
            )
        )


        # --------------------------
        # Summary
        # --------------------------

        print("\n=== HOLIDAY SUMMARY ===")

        print(
            holiday_calendar.summary()
        )


        # --------------------------
        # Business calendar
        # --------------------------

        business = BusinessCalendar(
            holiday_calendar
        )


        print("\n=== BUSINESS SUMMARY ===")

        print(
            business.summary(
                date(2026, 1, 1),
                date(2026, 12, 31),
            )
        )


        # --------------------------
        # Dimension calendar
        # --------------------------

        print("\n=== DIM CALENDAR SAMPLE ===")

        dim_calendar = generate_dim_calendar(
            date(2026, 1, 1),
            date(2026, 1, 10),
            business,
        )


        for row in dim_calendar:
            print(row)

        print("\n=== POLARS ===")

        df = calendar_to_polars(
            dim_calendar
        )

        print(df)


        print("\n=== PARQUET ===")

        calendar_to_parquet(
            dim_calendar,
            "dim_calendar_2026.parquet",
        )

        print(
            "Generated dim_calendar_2026.parquet"
        )

        crawler = FeriadosCrawler(
            client,
            concurrency=10,
        )


        national = await crawler.crawl_national(
            2026
        )

        print(
            "National:",
            len(national)
        )


        states = await crawler.crawl_states(
            2026
        )

        print(
            "States:",
            len(states)
        )



if __name__ == "__main__":
    asyncio.run(main())

