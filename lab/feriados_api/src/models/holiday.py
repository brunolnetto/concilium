from dataclasses import dataclass
from datetime import date


@dataclass(slots=True)
class HolidayRaw:

    date: date

    name: str

    type: str

    uf: str | None

    ibge: int | None

    year: int

    source: str = "feriadosapi"