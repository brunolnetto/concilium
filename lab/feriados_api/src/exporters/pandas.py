from __future__ import annotations

import pandas as pd

from ..models import CalendarDay


def calendar_to_pandas(
    days: list[CalendarDay],
) -> pd.DataFrame:

    return pd.DataFrame(
        [
            {
                "date_key": day.date_key,
                "date": day.date,

                "year": day.year,
                "month": day.month,
                "quarter": day.quarter,

                "weekday_number": day.weekday_number,
                "weekday_name": day.weekday_name,

                "is_weekend": day.is_weekend,

                "is_holiday": day.is_holiday,
                "holiday_name": day.holiday_name,
                "holiday_type": day.holiday_type,

                "is_business_day": day.is_business_day,
            }
            for day in days
        ]
    )