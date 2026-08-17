from __future__ import annotations

from dataclasses import asdict
from pathlib import Path

import duckdb

from ..exporters.polars import calendar_to_polars


def export_duckdb(
    data,
    database: str | Path,
    table: str = "holidays",
):
    """
    Export data into DuckDB.

    Accepts:
    - list[dataclass]
    - list[dict]
    - polars.DataFrame

    """

    database = str(database)

    connection = duckdb.connect(
        database
    )

    try:

        #
        # Convert input
        #

        if hasattr(data, "schema"):
            # Already a Polars dataframe
            df = data

        elif isinstance(data, list):

            if not data:
                return

            first = data[0]

            if hasattr(first, "__dataclass_fields__"):

                import polars as pl

                df = pl.DataFrame(
                    [
                        asdict(item)
                        for item in data
                    ]
                )

            elif isinstance(first, dict):

                import polars as pl

                df = pl.DataFrame(
                    data
                )

            else:
                raise TypeError(
                    f"Unsupported item type: {type(first)}"
                )

        else:

            raise TypeError(
                f"Unsupported data type: {type(data)}"
            )


        #
        # Register dataframe
        #

        connection.register(
            "input_df",
            df.to_arrow(),
        )


        #
        # Create table
        #

        connection.execute(
            f"""
            CREATE OR REPLACE TABLE {table}
            AS
            SELECT *
            FROM input_df
            """
        )


    finally:

        connection.close()