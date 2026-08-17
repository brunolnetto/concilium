from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Literal
from uuid import UUID


HolidayType = Literal[
    "NACIONAL",
    "ESTADUAL",
    "MUNICIPAL",
    "FACULTATIVO",
]


@dataclass(frozen=True, slots=True)
class Holiday:
    id: UUID
    date: date
    name: str
    type: HolidayType
    description: str | None
    uf: str | None
    ibge_code: int | None
    banking: bool

    @classmethod
    def from_api(
        cls,
        payload: dict,
    ) -> "Holiday":

        return cls(
            id=UUID(payload["id"]),
            date=parse_api_date(payload["data"]),
            name=payload["nome"],
            type=payload["tipo"],
            description=payload.get("descricao"),
            uf=payload.get("uf"),
            ibge_code=payload.get("codigo_ibge"),
            banking=payload.get("bancario", False),
        )


from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class HolidayRecord:

    date: date

    name: str

    level: str

    is_facultativo: bool

    is_bancario: bool

    uf: str | None

    ibge: int | None

    year: int

    holiday_key: str = ""


@dataclass(frozen=True, slots=True)
class CalendarDay:

    date: date

    date_key: int

    year: int
    month: int
    quarter: int

    weekday_number: int
    weekday_name: str

    is_weekend: bool

    is_holiday: bool
    holiday_name: str | None
    holiday_type: str | None

    is_business_day: bool


def parse_api_date(value: str) -> date:
    day, month, year = value.split("/")

    return date(
        int(year),
        int(month),
        int(day),
    )

