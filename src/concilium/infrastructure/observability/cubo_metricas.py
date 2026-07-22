"""CuboMetricas — cubo Gold sobre a fato FACT_METRIC_DATAPOINT (ADR-147).

Primeiro consumidor real da projeção dimensional de metrics (ADR-146) — Gold
nunca usou metrics antes deste cubo, mesmo com traces/logs já agregados.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

from .cubo_base import Cubo


@dataclass(frozen=True)
class CelulaMetrica:
    metric_name: str
    skill_id: str | None
    project_id: str | None
    tool_name: str | None
    date: str
    value: float


class CuboMetricas(Cubo[CelulaMetrica]):
    _sql_types: ClassVar[dict[str, str]] = {
        "metric_name": "TEXT",
        "skill_id": "TEXT",
        "project_id": "TEXT",
        "tool_name": "TEXT",
        "date": "TEXT",
        "value": "DOUBLE",
    }

    @classmethod
    def from_silver(cls, records: list[dict[str, Any]]) -> CuboMetricas:
        """Constrói o cubo a partir de records Silver metrics (normalize_metric_record, ADR-146)."""
        celulas = tuple(
            CelulaMetrica(
                metric_name=r.get("metric_name", ""),
                skill_id=r.get("skill_id"),
                project_id=r.get("project_id"),
                tool_name=r.get("tool_name"),
                date=(r.get("ts") or "")[:10],
                value=float(r.get("value", 0.0)),
            )
            for r in records
        )
        return cls(celulas=celulas)
