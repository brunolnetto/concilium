from __future__ import annotations

import sqlite3
from pathlib import Path
from datetime import datetime, timezone

from .models import (
    CrawlStatus,
    CrawlTask,
)


class CrawlCheckpoint:


    def __init__(
        self,
        database: str | Path = "crawler.db",
    ):

        self.connection = sqlite3.connect(
            database
        )

        self.connection.execute(
            """
            CREATE TABLE IF NOT EXISTS crawl_checkpoint (

                scope TEXT NOT NULL,

                year INTEGER NOT NULL,

                uf TEXT NOT NULL DEFAULT '',

                ibge INTEGER NOT NULL DEFAULT -1,

                status TEXT NOT NULL,

                records INTEGER DEFAULT 0,

                payload TEXT,

                error TEXT,

                updated_at TEXT NOT NULL,

                PRIMARY KEY(
                    scope,
                    year,
                    uf,
                    ibge
                )
            )
            """
        )

        try:
            self.connection.execute(
                "ALTER TABLE crawl_checkpoint ADD COLUMN payload TEXT"
            )
        except sqlite3.OperationalError:
            pass

        self.connection.commit()



    def is_done(
        self,
        task: CrawlTask,
    ) -> bool:


        row = self.connection.execute(
            """
            SELECT status
            FROM crawl_checkpoint

            WHERE
                scope = ?
            AND year = ?

            AND uf = ?

            AND ibge = ?
            """,
            (
                task.scope.value,
                task.year,
                task.uf or "",
                task.ibge or -1,
            ),
        ).fetchone()


        return (
            row is not None
            and row[0]
            ==
            CrawlStatus.SUCCESS.value
        )



    def save(
        self,
        task: CrawlTask,
        status: CrawlStatus,
        *,
        records: int = 0,
        payload: str | None = None,
        error: str | None = None,
    ):


        self.connection.execute(
            """
            INSERT INTO crawl_checkpoint
            (
                scope,
                year,
                uf,
                ibge,
                status,
                records,
                payload,
                error,
                updated_at
            )

            VALUES (?,?,?,?,?,?,?,?,?)

            ON CONFLICT(
                scope,
                year,
                uf,
                ibge
            )

            DO UPDATE SET

                status =
                    excluded.status,

                records =
                    excluded.records,

                payload =
                    excluded.payload,

                error =
                    excluded.error,

                updated_at =
                    excluded.updated_at

            """,
            (
                task.scope.value,
                task.year,
                task.uf or "",
                task.ibge or -1,
                status.value,
                records,
                payload,
                error,
                datetime.now(
                    timezone.utc
                ).isoformat(),
            ),
        )


        self.connection.commit()


    def get_payload(
        self,
        task: CrawlTask,
    ) -> str | None:

        row = self.connection.execute(
            """
            SELECT payload
            FROM crawl_checkpoint

            WHERE
                scope = ?
            AND year = ?

            AND uf = ?

            AND ibge = ?
            """,
            (
                task.scope.value,
                task.year,
                task.uf or "",
                task.ibge or -1,
            ),
        ).fetchone()

        return row[0] if row else None


    def stats(self):

        cursor = self.connection.execute(
            """
            SELECT
                status,
                COUNT(*)

            FROM crawl_checkpoint

            GROUP BY status
            """
        )


        return dict(cursor.fetchall())