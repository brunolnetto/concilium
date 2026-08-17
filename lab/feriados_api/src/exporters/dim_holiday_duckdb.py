from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path

import duckdb

from ..transformers.dim_holiday import DimHoliday


def _compute_diff(
    old: tuple | None,
    canonical_name: str,
    aliases: list[str],
    date,
    occurrences: list[dict],
) -> dict | None:

    if old is None:
        return None

    old_canonical_name, old_aliases, old_date, old_occurrences = old

    changes = {}

    if old_canonical_name != canonical_name:
        changes["canonical_name"] = {
            "old": old_canonical_name,
            "new": canonical_name,
        }

    if set(old_aliases) != set(aliases):
        changes["aliases"] = {
            "old": old_aliases,
            "new": aliases,
        }

    if old_date != date:
        changes["date"] = {
            "old": str(old_date),
            "new": str(date),
        }

    if old_occurrences != occurrences:
        changes["occurrences"] = {
            "old": old_occurrences,
            "new": occurrences,
        }

    return changes or None


def export_dim_holiday(
    dim_holidays: list[DimHoliday],
    database: str | Path,
    table: str = "dim_holiday",
):
    """
    Upserts dim_holiday rows keyed by (holiday_key, year) instead of
    replacing the table, so re-running the pipeline for a year updates
    that year's rows in place while other years already in the table
    are left untouched. The `diff` column records what changed on this
    upsert compared to the row's previous value (null on first insert
    or when nothing changed).
    """

    if not dim_holidays:
        return

    expected_columns = {
        "holiday_key",
        "year",
        "canonical_name",
        "aliases",
        "date",
        "occurrences",
        "diff",
    }

    connection = duckdb.connect(str(database))

    try:

        existing_columns = {
            row[0]
            for row in connection.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = ?",
                [table],
            ).fetchall()
        }

        # A table from an older schema version can't be upserted into
        # — drop and let it be recreated below.
        if existing_columns and existing_columns != expected_columns:
            connection.execute(f"DROP TABLE {table}")

        connection.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {table} (

                holiday_key VARCHAR,

                year INTEGER,

                canonical_name VARCHAR,

                aliases VARCHAR[],

                date DATE,

                occurrences STRUCT(
                    uf VARCHAR,
                    ibge INTEGER,
                    level VARCHAR,
                    is_facultativo BOOLEAN,
                    is_bancario BOOLEAN
                )[],

                diff VARCHAR,

                PRIMARY KEY (holiday_key, year)
            )
            """
        )

        holiday_keys = list({d.holiday_key for d in dim_holidays})

        placeholders = ",".join("?" * len(holiday_keys))

        existing_by_key: dict[tuple[str, int], tuple] = {
            (row[0], row[1]): row[2:]
            for row in connection.execute(
                f"""
                SELECT holiday_key, year, canonical_name, aliases, date, occurrences
                FROM {table}
                WHERE holiday_key IN ({placeholders})
                """,
                holiday_keys,
            ).fetchall()
        }

        rows = []

        for d in dim_holidays:

            occurrences = [asdict(o) for o in d.occurrences]

            diff = _compute_diff(
                existing_by_key.get((d.holiday_key, d.year)),
                d.canonical_name,
                d.aliases,
                d.date,
                occurrences,
            )

            rows.append(
                (
                    d.holiday_key,
                    d.year,
                    d.canonical_name,
                    d.aliases,
                    d.date,
                    occurrences,
                    json.dumps(diff, ensure_ascii=False, default=str)
                    if diff
                    else None,
                )
            )

        connection.executemany(
            f"""
            INSERT INTO {table}
            (holiday_key, year, canonical_name, aliases, date, occurrences, diff)
            VALUES (?, ?, ?, ?, ?, ?, ?)

            ON CONFLICT (holiday_key, year) DO UPDATE SET

                canonical_name = EXCLUDED.canonical_name,
                aliases = EXCLUDED.aliases,
                date = EXCLUDED.date,
                occurrences = EXCLUDED.occurrences,
                diff = EXCLUDED.diff
            """,
            rows,
        )

    finally:

        connection.close()
