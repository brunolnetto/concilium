from __future__ import annotations

from datetime import date, timedelta

from ..models import Holiday


class HolidayCalendar:

    def __init__(
        self,
        holidays: list[Holiday],
    ):
        self._holidays = {
            holiday.date: holiday
            for holiday in holidays
        }


    def holidays(
        self,
    ) -> list[Holiday]:

        return sorted(
            self._holidays.values(),
            key=lambda h: h.date,
        )


    def is_holiday(
        self,
        day: date,
    ) -> bool:

        return day in self._holidays


    def holiday(
        self,
        day: date,
    ) -> Holiday | None:

        return self._holidays.get(day)


    def is_business_day(
        self,
        day: date,
        *,
        saturday: bool = False,
    ) -> bool:

        if day in self._holidays:
            return False

        if day.weekday() == 6:
            return False

        if day.weekday() == 5:
            return saturday

        return True


    def business_days(
        self,
        start: date,
        end: date,
    ) -> list[date]:

        result = []

        current = start

        while current <= end:

            if self.is_business_day(current):
                result.append(current)

            current += timedelta(days=1)

        return result


    def summary(self) -> dict:
        return {
            "total_holidays": len(self._holidays),
            "national": sum(
                h.type == "NACIONAL"
                for h in self._holidays.values()
            ),
            "state": sum(
                h.type == "ESTADUAL"
                for h in self._holidays.values()
            ),
            "municipal": sum(
                h.type == "MUNICIPAL"
                for h in self._holidays.values()
            ),
        }