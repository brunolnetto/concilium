"""CuboToolInvocations — cubo Gold sobre a fato FACT_TOOL_INVOCATION (ADR-147).

Primeiro cubo sobre o 4º signal_type do medalhão (tool_invocations, ADR-112
extensão) — a duração é calculada aqui (finished_at - started_at), já que
Silver guarda os dois timestamps brutos, não a duração pronta.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, ClassVar

from .cubo_base import Cubo


def _duration_ms(started_at: str, finished_at: str) -> int:
    """Duração em ms entre dois timestamps ISO-8601. 0 se ausentes ou malformados —
    best-effort, nunca deve derrubar a construção do cubo por um registro ruim."""
    if not started_at or not finished_at:
        return 0
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
        return max(0, round((end - start).total_seconds() * 1000))
    except ValueError:
        return 0


@dataclass(frozen=True)
class CelulaToolInvocation:
    tool_name: str
    user_id: str | None
    device_id: str | None
    status: str
    date: str
    duration_ms: int


class CuboToolInvocations(Cubo[CelulaToolInvocation]):
    _sql_types: ClassVar[dict[str, str]] = {
        "tool_name": "TEXT",
        "user_id": "TEXT",
        "device_id": "TEXT",
        "status": "TEXT",
        "date": "TEXT",
        "duration_ms": "INTEGER",
    }

    @classmethod
    def from_silver(cls, records: list[dict[str, Any]]) -> CuboToolInvocations:
        """Constrói o cubo a partir de records Silver tool_invocations (normalize_tool_invocation_record)."""
        celulas = tuple(
            CelulaToolInvocation(
                tool_name=r.get("tool_name", ""),
                user_id=r.get("user_id"),
                device_id=r.get("device_id"),
                status=r.get("status", ""),
                date=(r.get("started_at") or "")[:10],
                duration_ms=_duration_ms(r.get("started_at", ""), r.get("finished_at", "")),
            )
            for r in records
        )
        return cls(celulas=celulas)
