from __future__ import annotations

import duckdb

from ..models import CalendarDay
from ..exporters.polars import calendar_to_polars


def calendar_to_duckdb(
    days: list[CalendarDay],
    database: str = ":memory:",
    table_name: str = "dim_calendar",
):

    df = calendar_to_polars(days)

    conn = duckdb.connect(database)

    conn.register(
        "calendar_df",
        df,
    )

    conn.execute(
        f"""
        CREATE OR REPLACE TABLE {table_name}
        AS
        SELECT *
        FROM calendar_df
        """
    )

    return conn


def load_holidays(
    records,
    database="feriados.duckdb",
):

    con = duckdb.connect(database)


    con.execute(
        """
        CREATE TABLE IF NOT EXISTS dim_holiday (

            date DATE,

            name VARCHAR,

            level VARCHAR,

            is_facultativo BOOLEAN,

            is_bancario BOOLEAN,

            uf VARCHAR,

            ibge INTEGER,

            year INTEGER,

            holiday_key VARCHAR

        )
        """
    )


    con.executemany(
        """
        INSERT INTO dim_holiday VALUES
        (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        [
            (
                r.date,
                r.name,
                r.level,
                r.is_facultativo,
                r.is_bancario,
                r.uf,
                r.ibge,
                r.year,
                r.holiday_key,
            )
            for r in records
        ],
    )


    con.close()