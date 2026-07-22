"""CuboSpans — cubo Gold sobre a fato FACT_SPAN (ADR-147).

Substitui a leitura ad-hoc de GoldAggregator.build_sli_diario por uma tupla
imutável de células no grão atômico, consultável por .slice()/.query() com
qualquer combinação de dimensões — não só (date, skill_id).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .cubo_base import Cubo


@dataclass(frozen=True)
class CelulaSpan:
    skill_id: str | None
    project_id: str | None
    tool_name: str | None
    user_id: str | None
    status: str
    date: str
    duration_ms: int


class CuboSpans(Cubo[CelulaSpan]):
    _sql_types: ClassVar[dict[str, str]] = {
        "skill_id": "TEXT",
        "project_id": "TEXT",
        "tool_name": "TEXT",
        "user_id": "TEXT",
        "status": "TEXT",
        "date": "TEXT",
        "duration_ms": "INTEGER",
    }

    @classmethod
    def from_silver(cls, records: list[dict[str, Any]]) -> CuboSpans:
        """Constrói o cubo a partir de records Silver traces (normalize_span_record)."""
        celulas = tuple(
            CelulaSpan(
                skill_id=r.get("skill_id"),
                project_id=r.get("project_id"),
                tool_name=r.get("tool_name"),
                user_id=r.get("user_id"),
                status=r.get("status", ""),
                date=(r.get("start_ts") or "")[:10],
                duration_ms=int(r.get("duration_ms", 0)),
            )
            for r in records
        )
        return cls(celulas=celulas)
