from ..crawler import FeriadosCrawler


class FeriadosAPISource:


    def __init__(
        self,
        client,
        *,
        year,
        states=True,
        **kwargs,
    ):

        self.client = client

        self.year = year

        self.states = states



    async def extract(self):

        crawler = FeriadosCrawler(
            self.client,
            workers=5,
        )


        records=[]


        async for result in crawler.crawl_states(
            self.year
        ):

            if result.payload:

                records.extend(
                    result.payload
                )


        return records