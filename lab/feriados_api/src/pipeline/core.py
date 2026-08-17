from tqdm.auto import tqdm

from ..crawler import FeriadosCrawler
from ..crawler.capitals import STATE_CAPITALS
from ..transformers.holidays import normalize_holidays


class HolidayPipeline:


    def __init__(
        self,
        crawler,
        config,
    ):
        self.crawler = crawler
        self.config = config



    async def run(self):

        records = []

        states = await self.crawler.client.states()

        progress = tqdm(
            total=states["total"],
            desc="States",
            unit="state",
        )

        async for result in self.crawler.crawl_states(
            self.config.year
        ):

            progress.update(1)

            if result.payload:

                records.extend(
                    result.payload
                )

        progress.close()

        if self.config.include_municipalities:

            # crawl_municipalities() already covers the 27 capitals,
            # so it replaces the capitals-only crawl below.

            municipalities = await self.crawler.client.all_municipalities()

            city_progress = tqdm(
                total=len(municipalities),
                desc="Municipalities",
                unit="city",
            )

            async for result in self.crawler.crawl_municipalities(
                self.config.year
            ):

                city_progress.update(1)

                if result.payload:

                    records.extend(
                        result.payload
                    )

            city_progress.close()

        else:

            capitals_progress = tqdm(
                total=len(STATE_CAPITALS),
                desc="Capitals",
                unit="capital",
            )

            async for result in self.crawler.crawl_capitals(
                self.config.year
            ):

                capitals_progress.update(1)

                if result.payload:

                    records.extend(
                        result.payload
                    )

            capitals_progress.close()

        records = self._deduplicate(records)

        data = normalize_holidays(
            records,
            year=self.config.year,
        )


        return data


    @staticmethod
    def _deduplicate(records):

        # The API assigns a stable id to each holiday, so the same
        # holiday appearing across multiple state/capital/facultativo
        # calls always carries the same id — dedupe on that instead of
        # (date, type, uf, ibge) so distinct holidays that happen to
        # share those fields (e.g. two different-named Nov 20 entries)
        # aren't collapsed into one.

        unique = {
            holiday.id: holiday
            for holiday in records
        }

        return list(unique.values())