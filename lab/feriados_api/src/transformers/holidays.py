from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.models import Holiday
from ..models import HolidayRecord


@dataclass(slots=True)
class DimHoliday:

    holiday_key: int

    date: datetime.date

    name: str

    holiday_type: str

    uf: str | None

    codigo_ibge: int | None

    is_national: bool
    is_state: bool
    is_municipal: bool

    bancario: bool


def holiday_key(holiday: Holiday) -> int:
    """
    Generates a deterministic surrogate key.

    YYYYMMDD + type hash component.
    """

    date_part = int(
        holiday.date.strftime("%Y%m%d")
    )

    type_part = {
        "NACIONAL": 1,
        "ESTADUAL": 2,
        "MUNICIPAL": 3,
    }.get(
        holiday.type,
        9,
    )

    return (
        date_part * 10
        + type_part
    )


def transform_holidays(
    holidays: list[Holiday],
) -> list[DimHoliday]:

    result = []

    seen = set()

    for holiday in holidays:

        #
        # Deduplication key
        #

        key = (
            holiday.date,
            holiday.name,
            holiday.type,
            holiday.uf,
            holiday.codigo_ibge,
        )

        if key in seen:
            continue

        seen.add(key)


        result.append(
            DimHoliday(

                holiday_key=holiday_key(
                    holiday
                ),

                date=holiday.date,

                name=holiday.name,

                holiday_type=holiday.type,

                uf=holiday.uf,

                codigo_ibge=holiday.codigo_ibge,

                is_national=(
                    holiday.type == "NACIONAL"
                ),

                is_state=(
                    holiday.type == "ESTADUAL"
                ),

                is_municipal=(
                    holiday.type == "MUNICIPAL"
                ),

                bancario=holiday.bancario,
            )
        )

    return result

def resolve_level(holiday) -> str:

    # Jurisdiction level is independent of the facultativo/compulsorio
    # status — the API collapses both into a single `tipo` field
    # ("FACULTATIVO" hides whether it's a national, state or municipal
    # holiday), so level is derived from uf/ibge_code instead of `type`.

    if holiday.ibge_code is not None:
        return "MUNICIPAL"

    if holiday.uf is not None:
        return "ESTADUAL"

    return "NACIONAL"


def normalize_holidays(
    payload,
    *,
    uf=None,
    year=None,
):

    holidays = []

    for item in payload:

        holidays.append(
            HolidayRecord(
                date=item.date,

                name=item.name,

                level=resolve_level(item),

                is_facultativo=item.type == "FACULTATIVO",

                is_bancario=item.banking,

                uf=item.uf if item.uf is not None else uf,

                ibge=item.ibge_code,

                year=year,
            )
        )

    return holidays