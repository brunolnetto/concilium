from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .calendar import HolidayCalendar


@dataclass(frozen=True, slots=True)
class BusinessDaySummary:
    start: date
    end: date
    total_days: int
    weekends: int
    holidays: int
    business_days: int


class BusinessCalendar:

    def __init__(
        self,
        calendar: HolidayCalendar,
    ):
        self.calendar = calendar


    def summary(
        self,
        start: date,
        end: date,
    ) -> BusinessDaySummary:

        total_days = 0
        weekends = 0
        holidays = 0
        business_days = 0

        current = start

        while current <= end:

            total_days += 1

            if current.weekday() >= 5:
                weekends += 1

            elif self.calendar.is_holiday(current):
                holidays += 1

            else:
                business_days += 1

            current += timedelta(days=1)


        return BusinessDaySummary(
            start=start,
            end=end,
            total_days=total_days,
            weekends=weekends,
            holidays=holidays,
            business_days=business_days,
        )