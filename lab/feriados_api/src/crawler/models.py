from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any


class CrawlScope(StrEnum):
    NATIONAL = "NATIONAL"
    STATE = "STATE"
    MUNICIPALITY = "MUNICIPALITY"


class CrawlStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


@dataclass(slots=True, frozen=True)
class CrawlTask:

    year: int

    scope: CrawlScope

    uf: str | None = None

    ibge: int | None = None


@dataclass(slots=True)
class CrawlResult:

    task: CrawlTask
    status: CrawlStatus

    records: int = 0
    payload: list[Any] | None = None
    error: Exception | None = None

    @property
    def success(self) -> bool:
        return self.status == CrawlStatus.SUCCESS

    @property
    def failed(self) -> bool:
        return self.status == CrawlStatus.FAILED

    @property
    def skipped(self) -> bool:
        return self.status == CrawlStatus.SKIPPED