from ..crawler import FeriadosCrawler


async def extract_states(
    crawler,
    year,
):

    records=[]

    async for result in crawler.crawl_states(
        year
    ):

        if result.status.value == "SUCCESS":

            records.append(
                result
            )

    return records