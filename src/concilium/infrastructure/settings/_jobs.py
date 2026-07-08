"""Settings (parte extraída de settings.py) — grupo _jobs."""

from __future__ import annotations

from dataclasses import dataclass

from ._core import _int


@dataclass(frozen=True)
class JobsSettings:
    """Configuração do sistema de jobs assíncronos de pipeline (ADR-102)."""

    max_concurrent_jobs: int
    """CONCILIUM__MAX_CONCURRENT_JOBS — máximo de jobs simultâneos no worker pool (default: 3)."""

    job_ttl_hours: int
    """CONCILIUM__JOB_TTL_HOURS — tempo de vida de jobs finalizados antes de GC (default: 24h)."""

    job_gc_interval_minutes: int
    """CONCILIUM__JOB_GC_INTERVAL_MINUTES — intervalo de garbage collection em minutos (default: 60)."""

    @classmethod
    def from_env(cls) -> JobsSettings:
        return cls(
            max_concurrent_jobs=_int("CONCILIUM__MAX_CONCURRENT_JOBS", 3),
            job_ttl_hours=_int("CONCILIUM__JOB_TTL_HOURS", 24),
            job_gc_interval_minutes=_int("CONCILIUM__JOB_GC_INTERVAL_MINUTES", 60),
        )


_jobs: JobsSettings | None = None


def get_jobs() -> JobsSettings:
    global _jobs
    if _jobs is None:
        _jobs = JobsSettings.from_env()
    return _jobs


