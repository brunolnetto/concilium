from __future__ import annotations

import asyncio
from dataclasses import replace
from typing import Any

import httpx

from .transformers.calendar import HolidayCalendar
from .exceptions import FeriadosAPIError
from .models import Holiday
from .rate_limit import AsyncRateLimiter


class FeriadosClient:

    BASE_URL = "https://feriadosapi.com/api/v1"
    RATE_LIMIT = 60  # requests per minute
    MAX_RETRIES = 3  # transient errors (e.g. the CDN's anti-bot checkpoint)

    def __init__(
        self,
        api_key: str,
        *,
        timeout: float = 30.0,
    ):
        self._client = httpx.AsyncClient(
            base_url=self.BASE_URL,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
            },
        )
        self._limiter = AsyncRateLimiter(
            self.RATE_LIMIT
        )


    async def __aenter__(self):
        return self


    async def __aexit__(self, *exc):
        await self.close()


    async def close(self):
        await self._client.aclose()


    async def _get(
        self,
        path: str,
        **params,
    ):

        last_error: FeriadosAPIError | None = None

        for attempt in range(self.MAX_RETRIES):

            await self._limiter.acquire()

            response = await self._client.get(
                path,
                params=params,
            )

            if not response.is_error:
                return response.json()

            last_error = FeriadosAPIError(
                response.status_code,
                response.text,
            )

            if attempt < self.MAX_RETRIES - 1:
                await asyncio.sleep(2**attempt)

        raise last_error


    # ---------------------------
    # Holidays
    # ---------------------------

    async def national_holidays(
        self,
        year: int,
        *,
        facultativos: bool = False,
        bancarios: bool = False,
    ) -> list[Holiday]:

        response = await self._get(
            "/feriados/nacionais",
            ano=year,
            facultativos=str(facultativos).lower(),
            bancarios=str(bancarios).lower(),
        )

        return self._parse_holidays(response)


    async def state_holidays(
        self,
        uf: str,
        year: int,
        *,
        facultativos: bool = False,
        bancarios: bool = False,
    ) -> list[Holiday]:

        response = await self._get(
            f"/feriados/estado/{uf.upper()}",
            ano=year,
            facultativos=str(facultativos).lower(),
            bancarios=str(bancarios).lower(),
        )

        return self._parse_holidays(response)


    async def city_holidays(
        self,
        ibge: int,
        year: int,
        *,
        facultativos: bool = False,
        bancarios: bool = False,
    ) -> list[Holiday]:

        response = await self._get(
            f"/feriados/cidade/{ibge}",
            ano=year,
            facultativos=str(facultativos).lower(),
            bancarios=str(bancarios).lower(),
        )

        holidays = self._parse_holidays(response)

        # The API never sets `codigo_ibge` on individual holiday
        # records, even for genuinely municipal ones — the city is
        # only identified in the response's top-level "cidade" block.
        city = (
            response.get("cidade")
            if isinstance(response, dict)
            else None
        )

        if city:
            holidays = [
                replace(holiday, ibge_code=city["ibge"])
                if holiday.type == "MUNICIPAL" and holiday.ibge_code is None
                else holiday
                for holiday in holidays
            ]

        return holidays


    def _parse_holidays(
        self,
        response: dict | list,
    ) -> list[Holiday]:

        if isinstance(response, dict):
            items = response.get("feriados", [])

        else:
            items = response


        holidays = [
            Holiday.from_api(item)
            for item in items
        ]

        return self._deduplicate(holidays)


    @staticmethod
    def _deduplicate(
        holidays: list[Holiday],
    ) -> list[Holiday]:

        unique: dict[
            tuple,
            Holiday
        ] = {}

        for holiday in holidays:

            key = (
                holiday.date,
                holiday.type,
                holiday.uf,
                holiday.ibge_code,
            )

            unique[key] = holiday


        return list(unique.values())


    # ---------------------------
    # Geography
    # ---------------------------

    async def states(self):

        return await self._get(
            "/estados"
        )


    async def municipalities(
        self,
        *,
        page: int = 1,
        limit: int = 100,
    ):

        return await self._get(
            "/municipios",
            page=page,
            limit=limit,
        )


    async def municipality(
        self,
        ibge: int,
    ):

        return await self._get(
            f"/municipio/{ibge}"
        )


    async def all_municipalities(self):

        page = 1
        municipalities = []

        while True:

            response = await self.municipalities(
                page=page,
                limit=100,
            )

            municipalities.extend(
                response["municipios"]
            )

            meta = response["meta"]

            if page >= meta["total_pages"]:
                break

            page += 1


        return municipalities

    async def holidays(
        self,
        year: int,
        *,
        uf: str | None = None,
        ibge: int | None = None,
    ) -> list[Holiday]:

        if ibge:
            return await self.city_holidays(
                ibge,
                year,
            )

        if uf:
            return await self.state_holidays(
                uf,
                year,
            )

        return await self.national_holidays(
            year,
        )


    async def calendar(
        self,
        year: int,
        *,
        uf: str | None = None,
        ibge: int | None = None,
    ) -> HolidayCalendar:

        holidays = await self.holidays(
            year,
            uf=uf,
            ibge=ibge,
        )

        return HolidayCalendar(
            holidays
        )


