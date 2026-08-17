from __future__ import annotations

from datetime import date, timedelta

from ..calendar import HolidayCalendar
from ..business import BusinessCalendar
from ..models import CalendarDay


def generate_dim_calendar(
    start: date,
    end: date,
    business_calendar: BusinessCalendar,
) -> list[CalendarDay]:

    rows: list[CalendarDay] = []

    current = start

    while current <= end:

        holiday = (
            business_calendar.calendar.holiday(
                current
            )
        )

        is_weekend = current.weekday() >= 5

        rows.append(
            CalendarDay(
                date=current,

                date_key=int(
                    current.strftime("%Y%m%d")
                ),

                year=current.year,
                month=current.month,

                quarter=(
                    (current.month - 1) // 3
                ) + 1,

                weekday_number=current.weekday(),

                weekday_name=current.strftime(
                    "%A"
                ),

                is_weekend=is_weekend,

                is_holiday=holiday is not None,

                holiday_name=(
                    holiday.name
                    if holiday
                    else None
                ),

                holiday_type=(
                    holiday.type
                    if holiday
                    else None
                ),

                is_business_day=(
                    business_calendar
                    .calendar
                    .is_business_day(current)
                ),
            )
        )

        current += timedelta(days=1)

    return rows