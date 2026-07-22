"""CuboLogs — cubo Gold sobre a fato FACT_LOG_EVENT (ADR-147).

Substitui a leitura ad-hoc de GoldAggregator.build_fallback_rate_por_skill e
CrossDomainBuilder por uma tupla imutável de células, consultável por
.slice()/.query() com qualquer combinação de dimensões — não só por skill ou
só por projeto.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .cubo_base import Cubo


@dataclass(frozen=True)
class CelulaLog:
    skill_id: str | None
    project_id: str | None
    user_id: str | None
    severity: str
    fallback_type: str | None
    date: str


class CuboLogs(Cubo[CelulaLog]):
    _sql_types: ClassVar[dict[str, str]] = {
        "skill_id": "TEXT",
        "project_id": "TEXT",
        "user_id": "TEXT",
        "severity": "TEXT",
        "fallback_type": "TEXT",
        "date": "TEXT",
    }

    @classmethod
    def from_silver(cls, records: list[dict[str, Any]]) -> CuboLogs:
        """Constrói o cubo a partir de records Silver logs (normalize_log_record)."""
        celulas = tuple(
            CelulaLog(
                skill_id=r.get("skill_id"),
                project_id=r.get("project_id"),
                user_id=r.get("user_id"),
                severity=r.get("severity", ""),
                fallback_type=r.get("fallback_type"),
                date=(r.get("ts") or "")[:10],
            )
            for r in records
        )
        return cls(celulas=celulas)
